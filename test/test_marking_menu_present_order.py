# !/usr/bin/python
# coding=utf-8
"""Regression: on reopen, the overlay must present with the target page current.

Bug (live report): after launching a standalone window from a submenu — which
hides the marking menu via ``hide()`` rather than the activation-key release —
the NEXT activation briefly showed the submenu the window was launched from
before snapping to the start menu.

Cause: ``_show_marking_menu`` presented the overlay window
(``_ensure_fullscreen_on_active_screen`` → ``showFullScreen()``) BEFORE
``setCurrentWidget`` selected the target page. The overlay is a translucent
(layered) window: when re-shown, the OS re-presents its last composed frame
and Qt only replaces it on the first repaint after the show — so the first
presented frame(s) of every reopen were the PREVIOUS gesture's surface.

Fix: geometry assignment stays first (``setCurrentWidget`` maps the anchor
through the overlay's geometry), but presentation is LAST — a hidden overlay
becomes visible only after the target page is current, so its first presented
frame is the correct menu. The invariant is scoped to the hidden→visible
reopen transition: construction (``__init__``) and the mid-gesture monitor hop
(``_ensure_fullscreen_on_active_screen``'s relocate-while-visible branch)
legitimately present without a page swap.

The harness exercises the REAL ``_show_marking_menu`` / ``setCurrentWidget`` /
``_ensure_fullscreen_on_active_screen`` / ``hide`` methods (unlike
``DriveableMarkingMenu``, which overrides them) with a stub switchboard, and
records the current page at each presentation.
"""
import logging
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
from uitk.widgets.marking_menu.overlay import Overlay


class _Page(QtWidgets.QWidget):
    """Minimal stand-in for a Switchboard-loaded menu page."""

    def __init__(self, name, tags, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self._tags = set(tags)
        self.tags = list(tags)
        self.is_initialized = True
        self.header = None
        self.ensure_on_screen = False

    def has_tags(self, tags):
        if isinstance(tags, str):
            tags = [tags]
        return any(t in self._tags for t in tags)


class _HeaderStub:
    """Mirrors uitk Header's pin contract: ``reset_pin_state`` no-ops unless
    the HEADER believes it's pinned, and syncs the window when it acts."""

    def __init__(self, window):
        self._window = window
        self.pinned = False

    def reset_pin_state(self):
        if not self.pinned:
            return
        self.pinned = False
        self._window.set_pinned(False)


class _PinnedPage(_Page):
    """Mirrors MainWindow's pin-gated ``setVisible`` (mainWindow.py) — a pinned
    page silently refuses ``hide()``. The dodge that ghosts a stale menu back
    on the next present."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned = False
        self.header = _HeaderStub(self)

    @property
    def pinned(self):
        return self._pinned

    def set_pinned(self, value):
        self._pinned = bool(value)

    def setVisible(self, visible):
        if not visible and self._pinned:
            return
        super().setVisible(visible)


class _StubHandlers:
    def __init__(self):
        self.marking_menu = None
        self.ui = None


class _StubSB:
    def __init__(self):
        self._uis = {}
        self._current_ui = None
        self.handlers = _StubHandlers()
        self.visible_windows = []

    def register_ui(self, ui):
        self._uis[ui.objectName()] = ui

    @property
    def current_ui(self):
        return self._current_ui

    @current_ui.setter
    def current_ui(self, ui):
        self._current_ui = ui

    @property
    def active_ui(self):
        return self._current_ui

    def get_ui(self, name):
        return self._current_ui if name is None else self._uis.get(name)

    def ui_history(self, *args, **kwargs):
        return []

    def get_widget(self, name, ui):
        return None


class _MouseTrackingStub:
    _input_logging_on = False

    def update_child_widgets(self):
        pass


class PresentProbeMarkingMenu(MarkingMenu):
    """Bypass ``__init__`` but keep every show/hide method REAL.

    ``showFullScreen`` records which page is current at the moment the window
    is presented — the frame the user sees first. (It maps to a plain
    ``show()`` so the test never opens a real full-screen window on a dev
    machine; visibility semantics are identical.)
    """

    def __init__(self, parent):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.logger = logging.getLogger("PresentProbeMarkingMenu")
        self.logger.setLevel(logging.CRITICAL)
        self.presented = []  # objectName of _current_widget at each present

        self.flushes = []  # (window_visible, shown-state page names) per repaint
        self._bindings = {"Key_F12": "hud#startmenu"}
        self._activation_key_str = "Key_F12"
        self._activation_key = QtCore.Qt.Key_F12
        self._activation_key_held = False
        self._standalone_suppress = False
        self._suppress_default_on_reentry = False
        self._non_default_shown = False
        self._current_widget = None
        self._submenu_cache = {}
        self._in_transition = False
        self._last_ui_history_check = None
        self._windows_to_restore = set()
        self._pending_hide_widget = None
        self._transitioning_to_window = False
        self._input_logging_on = False
        self._action_dispatched = False
        self._dim_snapshot_taken = False
        self._pending_show_timer = QtCore.QTimer()
        self._pending_show_timer.setSingleShot(True)
        self._chord_release_timer = None

        self.sb = _StubSB()
        self.overlay = Overlay(self, antialiasing=True)
        self.mouse_tracking = _MouseTrackingStub()

        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.resize(800, 600)

    def showFullScreen(self):
        self.presented.append(
            self._current_widget.objectName() if self._current_widget else None
        )
        QtWidgets.QWidget.show(self)

    def repaint(self):
        # Record each forced buffer flush: was the window visible, and which
        # stacked pages were still in shown-state at flush time.
        self.flushes.append(
            (
                self.isVisible(),
                sorted(
                    c.objectName()
                    for c in self.children()
                    if isinstance(c, QtWidgets.QWidget)
                    and not c.isHidden()
                    and getattr(c, "has_tags", None)
                    and c.has_tags(("startmenu", "submenu"))
                ),
            )
        )
        QtWidgets.QWidget.repaint(self)

    flushes: list

    def dim_other_windows(self):
        pass

    def restore_other_windows(self):
        pass


class TestReopenPresentOrder(QtBaseTestCase):
    """The reopened overlay's first presented frame must be the target menu."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = PresentProbeMarkingMenu(self.parent)
        self.track_widget(self.mm)

        self.hud = _Page("hud#startmenu", ["startmenu"], parent=self.mm)
        self.cam = _Page("cameras#startmenu", ["startmenu"], parent=self.mm)
        self.sub = _Page("normals#submenu", ["submenu"], parent=self.mm)
        for page in (self.hud, self.cam, self.sub):
            self.mm.sb.register_ui(page)
            self.track_widget(page)

    def tearDown(self):
        # start_gesture sets an application override cursor; make sure no
        # test path leaks it into the rest of the suite.
        while QtWidgets.QApplication.overrideCursor() is not None:
            QtWidgets.QApplication.restoreOverrideCursor()
        super().tearDown()

    def _reopen_after_submenu_launch_cycle(self):
        """The user's scenario: open → navigate to submenu → hide (standalone
        launch path) → reopen. Returns the presents recorded by the reopen."""
        self.mm._show_marking_menu(self.hud)
        self._drain_qt_events()

        # Hover-nav into the submenu (what _perform_transition commits).
        self.mm.setCurrentWidget(self.sub)
        self.mm.sb.current_ui = self.sub
        self._drain_qt_events()

        # The standalone-launch hide (same hide() the leaf-click path calls).
        self.mm.hide()
        self._drain_qt_events()
        self.assertTrue(self.mm.isHidden(), "precondition: overlay hidden")

        self.mm.presented.clear()
        self.mm.flushes.clear()  # so flush assertions see ONLY the reopen's
        self.mm._show_marking_menu(self.hud)  # the reopen
        self._drain_qt_events()
        return list(self.mm.presented)

    def test_reopen_presents_with_target_page_current(self):
        """At the moment the hidden overlay is presented, the target page must
        already be current — else the first frame the user sees is the
        previous gesture's surface (the reported flash)."""
        presented = self._reopen_after_submenu_launch_cycle()
        self.assertEqual(
            presented,
            ["hud#startmenu"],
            f"overlay presented with {presented!r} current — the window was "
            "shown before the target page was selected, so the first visible "
            "frame is the previous gesture's surface (the stale-menu flash).",
        )

    def test_reopen_ends_on_target_page_only(self):
        """End-state sanity: reopen shows the start menu, not the submenu."""
        self._reopen_after_submenu_launch_cycle()
        self.assertTrue(self.mm.isVisible())
        self.assertIs(self.mm._current_widget, self.hud)
        self.assertTrue(self.hud.isVisible())
        self.assertFalse(self.sub.isVisible())

    def test_hide_flushes_cleared_frame_while_still_visible(self):
        """hide() must force a repaint AFTER the pages are down but WHILE the
        window is still visible. The overlay is a layered (translucent)
        window: the OS re-presents its last composed frame on the next show,
        and Qt repaints only after that present — so stale menu pixels left
        in the buffer here flash on every reopen ('the previous submenu
        flashes momentarily on first show'). Flushing with the pages hidden
        composes an empty translucent frame — the retained buffer becomes
        invisible instead of stale."""
        self.mm._show_marking_menu(self.hud)
        self.mm.setCurrentWidget(self.sub)
        self.mm.sb.current_ui = self.sub
        self._drain_qt_events()

        self.mm.flushes.clear()
        self.mm.hide()
        self._drain_qt_events()

        clean_flushes = [
            (visible, pages)
            for visible, pages in self.mm.flushes
            if visible and not pages
        ]
        self.assertTrue(
            clean_flushes,
            f"hide() never flushed a cleared frame (flushes={self.mm.flushes!r}) "
            "— the layered-window buffer keeps the old menu's pixels and "
            "re-presents them on the next show.",
        )

    def test_reopen_pushes_fresh_frame_after_present(self):
        """After presenting on reopen, the fresh frame must be pushed
        immediately (forced repaint) rather than left to the host's next
        paint cycle — under a busy DCC loop that gap is user-visible."""
        presented = self._reopen_after_submenu_launch_cycle()
        self.assertEqual(presented, ["hud#startmenu"])  # sanity (covered above)
        post_present_flushes = [
            (visible, pages)
            for visible, pages in self.mm.flushes
            if visible and pages == ["hud#startmenu"]
        ]
        self.assertTrue(
            post_present_flushes,
            f"no immediate frame push after the present (flushes="
            f"{self.mm.flushes!r}) — the cleared retained frame stays on "
            "screen until the host event loop repaints.",
        )

    def test_visible_menu_switch_does_not_represent(self):
        """A chord switch while the overlay is already visible must not
        re-present the window (no extra show calls mid-gesture)."""
        self.mm._show_marking_menu(self.hud)
        self._drain_qt_events()
        self.mm.presented.clear()

        self.mm._show_marking_menu(self.cam)
        self._drain_qt_events()
        self.assertEqual(
            self.mm.presented,
            [],
            "switching menus on a visible overlay must not re-present it",
        )
        self.assertIs(self.mm._current_widget, self.cam)


class TestHideDefeatsPinnedPages(QtBaseTestCase):
    """MainWindow.setVisible is pin-gated — a pinned stacked page silently
    refuses hide(). MarkingMenu.hide() must unpin BEFORE hiding (the old
    order reset the pin AFTER the failed hide, leaving the page in
    shown-state), and must sweep any page that dodged an earlier hide —
    a shown-state child re-shows with the overlay on the next present:
    'the submenu that launched the window still shows on next key_show
    press'."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

        self.parent = QtWidgets.QWidget()
        self.parent.resize(400, 400)
        self.parent.show()
        self.track_widget(self.parent)

        self.mm = PresentProbeMarkingMenu(self.parent)
        self.track_widget(self.mm)

        self.hud = _Page("hud#startmenu", ["startmenu"], parent=self.mm)
        self.sub = _PinnedPage("normals#submenu", ["submenu"], parent=self.mm)
        for page in (self.hud, self.sub):
            self.mm.sb.register_ui(page)
            self.track_widget(page)

    def tearDown(self):
        while QtWidgets.QApplication.overrideCursor() is not None:
            QtWidgets.QApplication.restoreOverrideCursor()
        super().tearDown()

    def _navigate_to_pinned_submenu(self):
        self.mm._show_marking_menu(self.hud)
        self.mm.setCurrentWidget(self.sub)
        self.mm.sb.current_ui = self.sub
        self._drain_qt_events()

    def test_hide_unpins_current_page_before_hiding(self):
        """A pinned CURRENT page must end hide() explicitly hidden — the old
        hide-then-unpin order left it in shown-state (hide vetoed by the pin
        gate, pin cleared afterwards, nothing re-attempted the hide)."""
        self._navigate_to_pinned_submenu()
        self.sub.header.pinned = True
        self.sub.set_pinned(True)

        self.mm.hide()
        self._drain_qt_events()
        self.assertTrue(
            self.sub.isHidden(),
            "pinned page survived hide() in shown-state — it will ghost back "
            "on the next present.",
        )
        self.assertFalse(self.sub.pinned, "hide() must also clear the pin")

        # And the reopen must not resurrect it.
        self.mm._show_marking_menu(self.hud)
        self._drain_qt_events()
        self.assertFalse(self.sub.isVisible())

    def test_hide_unpins_page_with_desynced_header(self):
        """Window pinned but header not synced: Header.reset_pin_state no-ops
        (it early-returns unless the HEADER is pinned), so hide() must also
        clear the WINDOW-level pin — that's the flag setVisible consults."""
        self._navigate_to_pinned_submenu()
        self.sub.set_pinned(True)  # header.pinned stays False

        self.mm.hide()
        self._drain_qt_events()
        self.assertTrue(self.sub.isHidden())
        self.assertFalse(self.sub.pinned)

    def test_hide_sweeps_noncurrent_dodged_page(self):
        """A pinned page that already dodged a TRANSITION hide (it is no
        longer current) must still be caught by hide()'s sweep."""
        self._navigate_to_pinned_submenu()
        self.sub.header.pinned = True
        self.sub.set_pinned(True)

        # Navigate away: setCurrentWidget's hide of the pinned page is vetoed.
        self.mm.setCurrentWidget(self.hud)
        self.mm.sb.current_ui = self.hud
        self.assertTrue(self.sub.isVisible(), "precondition: pin dodged the hide")

        self.mm.hide()
        self._drain_qt_events()
        self.assertTrue(
            self.sub.isHidden(),
            "non-current dodged page survived hide() — the sweep must catch "
            "every shown-state stacked page, not just the current one.",
        )

    def test_bypassed_hide_also_sweeps(self):
        """A hide that bypasses hide() — setVisible(False), the path
        hideEvent's safety net exists for — must still sweep pinned pages;
        otherwise the ghost survives exactly when the normal cleanup was
        skipped."""
        self._navigate_to_pinned_submenu()
        self.sub.header.pinned = True
        self.sub.set_pinned(True)

        self.mm.setVisible(False)  # bypasses MarkingMenu.hide()
        self._drain_qt_events()
        self.assertTrue(
            self.sub.isHidden(),
            "pinned page survived a bypassed hide in shown-state — it will "
            "ghost back on the next present.",
        )
        self.assertFalse(self.sub.pinned)

    def test_hide_on_already_hidden_overlay_still_sweeps(self):
        """hide() on an ALREADY-hidden overlay (e.g. retire()) must still
        clear a shown-state ghost. Requires the sweep to test the child's
        own isHidden() — isVisible() is False for every child under a hidden
        parent, so a visibility-based sweep is blind here."""
        self._navigate_to_pinned_submenu()
        self.mm.hide()  # normal hide; submenu was NOT pinned yet -> hidden
        self._drain_qt_events()

        # Manufacture a ghost while the overlay is hidden: shown-state page
        # under a hidden parent (isHidden False, isVisible False).
        self.sub.show()
        self.sub.header.pinned = True
        self.sub.set_pinned(True)
        self.assertFalse(self.sub.isHidden(), "precondition: shown-state ghost")
        self.assertFalse(self.sub.isVisible(), "precondition: parent hidden")

        self.mm.hide()  # second hide on an already-hidden overlay
        self._drain_qt_events()
        self.assertTrue(
            self.sub.isHidden(),
            "ghost under an already-hidden overlay survived hide() — the "
            "sweep must test child.isHidden(), not child.isVisible().",
        )


if __name__ == "__main__":
    unittest.main()
