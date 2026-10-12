# !/usr/bin/python
# coding=utf-8
"""Scoped preloading + cold-first-show positioning for MarkingMenu.

Live report (Maya): the FIRST key_show press doesn't behave like every later
one — "it feels like it hasn't been initialized yet."

Cause: a cold page pays its entire initialization inside the first gesture.
``show(target)`` loads the .ui and runs ``_init_ui``, but the page's REAL
first-show work (``MainWindow.showEvent``: ``register_children`` slot wiring,
QSS polish, ``fit_height_to_content``) only fires when the hidden overlay
presents — which ``_show_marking_menu`` deliberately does LAST, *after*
``setCurrentWidget`` has already centered the page on the gesture anchor. So
on the first activation the page is positioned against its pre-init geometry,
then visibly settles (resize/off-center jump) once the present delivers the
first showEvent. Every later activation measures settled geometry and is
consistent.

Fix, two complementary parts (both under test here):

* ``preload_menus`` / ``preload=True`` — scoped preloading: warm the distinct
  binding-target menus (never the whole UI registry) through the real show
  path while nothing paints, using construction's suppressed-present trick
  (``WA_DontShowOnScreen``). The first activation then IS just another reopen.
* ``_show_marking_menu`` cold-show re-center — the backstop for any page that
  still reaches the activation path uninitialized (preload off, retargeted
  bindings): after the present delivers the page's first showEvent, re-center
  it on the same anchor against its settled geometry.
"""

import itertools
import os
import unittest
from unittest import mock

from qtpy import QtCore, QtGui, QtWidgets

import pythontk as ptk
from conftest import QtBaseTestCase, QtWait, write_ui_file
from uitk.widgets.marking_menu._marking_menu import MarkingMenu
from uitk.widgets.menuButton import MenuButton


def _make_central(fitted_height: int = 90) -> QtWidgets.QWidget:
    """A central widget whose settled (fitted) height is far below the 600px
    fallback ``_init_ui`` resizes cold pages to — so a first show that fits
    content AFTER positioning is detectably mis-centered."""
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    button = QtWidgets.QPushButton("leaf")
    button.setObjectName("b000")
    button.setFixedHeight(fitted_height)
    layout.addWidget(button)
    return central


class _PumpsOnFirstShow(QtWidgets.QWidget):
    """A page child whose first show pumps the event loop, as a slot init that
    builds a Maya native menu does (``MayaNativeMenus._populate_menu``)."""

    _pumped = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._pumped:
            self._pumped = True
            QtWidgets.QApplication.processEvents()


class _PreloadCase(QtBaseTestCase):
    """Shared harness: a REAL MarkingMenu + Switchboard, with real MainWindow
    pages registered via ``sb.add_ui`` (genuine ``is_initialized`` /
    first-show semantics, unlike the stub harnesses in sibling test files)."""

    BINDINGS = {
        "Key_F12": "hud#startmenu",
        "Key_F12|RightButton": "main#startmenu",
    }

    def setUp(self):
        super().setUp()
        self._mms = []

    def tearDown(self):
        # Retire BEFORE the base tearDown deletes widgets — retiring a
        # deleted MarkingMenu hits its C++-dead children (noisy RuntimeError
        # tracebacks in the log, even though retire swallows them).
        for mm in self._mms:
            try:
                mm.retire()
            except RuntimeError:
                pass
        super().tearDown()

    def _make_mm(self, context_tag: str, **kwargs) -> MarkingMenu:
        # Unique context_tags per test: the bindings store is host-namespaced,
        # so this keeps each test's persisted bindings isolated from the rest
        # of the (QSettings-sandboxed) suite.
        mm = MarkingMenu(
            parent=None,
            bindings=dict(self.BINDINGS),
            context_tags={context_tag},
            **kwargs,
        )
        self.track_widget(mm)
        self._mms.append(mm)
        return mm

    def _add_page(self, mm: MarkingMenu, name: str) -> QtWidgets.QWidget:
        page = mm.sb.add_ui(name, widget=_make_central(), tags={"startmenu"})
        self.track_widget(page)
        return page


class TestScopedPreload(_PreloadCase):
    """``preload_menus`` warms exactly the binding targets, without presenting."""

    def test_preload_initializes_binding_targets_without_presenting(self):
        mm = self._make_mm("t_preload_sync")
        hud = self._add_page(mm, "hud#startmenu")
        main = self._add_page(mm, "main#startmenu")
        unbound = self._add_page(mm, "unbound#startmenu")

        mm.preload_menus(defer=False)

        self.assertTrue(
            hud.is_initialized and main.is_initialized,
            "preload must run each binding target's first-show initialization",
        )
        self.assertFalse(
            unbound.is_initialized,
            "preload is SCOPED to binding targets — it must not walk the "
            "whole UI registry",
        )
        self.assertTrue(
            mm.isHidden(), "warming must never present the overlay on screen"
        )
        self.assertFalse(
            mm.testAttribute(QtCore.Qt.WA_DontShowOnScreen),
            "present-suppression must not leak past the warm-up",
        )
        self.assertFalse(hud.isVisible(), "warmed pages must end hidden")
        self.assertFalse(main.isVisible(), "warmed pages must end hidden")

    def test_preload_is_idempotent(self):
        mm = self._make_mm("t_preload_idem")
        hud = self._add_page(mm, "hud#startmenu")
        self._add_page(mm, "main#startmenu")

        mm.preload_menus(defer=False)
        self.assertTrue(hud.is_initialized)
        # Second run must skip initialized pages (and not error).
        mm.preload_menus(defer=False)
        self.assertTrue(mm.isHidden())

    def test_preload_survives_unresolvable_target(self):
        """A binding target with no registered UI (e.g. a host-synthesized
        menu) is skipped — preload must never break on it."""
        mm = self._make_mm("t_preload_missing")
        hud = self._add_page(mm, "hud#startmenu")
        # "main#startmenu" is deliberately NOT registered.

        mm.preload_menus(defer=False)
        self.assertTrue(hud.is_initialized)
        self.assertTrue(mm.isHidden())

    def test_preload_chain_survives_tagless_target(self):
        """A target resolving to an object without the tag surface (a plain
        QWidget) must be skipped — and must not break the deferred timer
        chain or strand the queue non-None (a stranded queue dead-ends every
        later preload_menus call: they merge into a run no timer services)."""
        mm = self._make_mm("t_preload_tagless")
        hud = self._add_page(mm, "hud#startmenu")
        bare = self.track_widget(QtWidgets.QWidget())
        bare.setObjectName("bare#startmenu")
        mm.sb.loaded_ui["bare#startmenu"] = bare

        mm.preload_menus(names=["bare#startmenu", "hud#startmenu"])
        for _ in range(10):
            if hud.is_initialized:
                break
            self._drain_qt_events()
        self.assertTrue(
            hud.is_initialized,
            "the warm-up chain must continue past a tag-less target",
        )
        self.assertIsNone(mm._preload_queue, "queue must not be stranded")

    def test_sync_preload_drains_inflight_deferred_queue(self):
        """A defer=False caller landing while a deferred run is in flight
        must still warm everything before returning (splash-screen /
        test-harness contract) — not silently hand its names to the
        deferred timer chain."""
        mm = self._make_mm("t_preload_merge")
        hud = self._add_page(mm, "hud#startmenu")
        main = self._add_page(mm, "main#startmenu")

        mm.preload_menus()  # deferred; its 0-delay timer not yet serviced
        mm.preload_menus(defer=False)  # sync caller drains the merged queue
        self.assertTrue(
            hud.is_initialized and main.is_initialized,
            "defer=False must warm synchronously even while a deferred run "
            "is in flight",
        )
        self.assertIsNone(mm._preload_queue)
        self._drain_qt_events()  # the stale deferred timer must no-op
        self.assertTrue(mm.isHidden())

    def test_constructor_flag_preloads_deferred(self):
        mm = self._make_mm("t_preload_ctor", preload=True)
        hud = self._add_page(mm, "hud#startmenu")
        main = self._add_page(mm, "main#startmenu")

        # The ctor schedules a staggered warm-up (one page per event-loop
        # tick); drain until it completes.
        for _ in range(20):
            if hud.is_initialized and main.is_initialized:
                break
            self._drain_qt_events()
        self.assertTrue(
            hud.is_initialized and main.is_initialized,
            "preload=True must warm the binding targets once the event loop spins",
        )
        self.assertTrue(mm.isHidden())

    def test_a_host_loop_only_preload_waits_out_a_script_pumping_events(self):
        """``PRELOAD_ONLY_FROM_HOST_LOOP``: a tick fired from a Python caller's
        ``processEvents`` -- a script pumping events -- waits rather than build a
        page mid-script, and the warm-up resumes once allowed.

        Regression: a preload tick fired inside mayatk's test_shot_manifest
        (``_menu`` -> ``processEvents``) built ``hud#startmenu`` there and
        faulted Maya iterating ``topLevelWidgets()``.
        """
        mm = self._make_mm("t_preload_host_loop")
        mm.PRELOAD_ONLY_FROM_HOST_LOOP = True
        hud = self._add_page(mm, "hud#startmenu")

        mm.preload_menus()
        for _ in range(5):
            self._drain_qt_events()  # Python pumping: every tick has a caller

        self.assertFalse(hud.is_initialized, "a page was built inside a script")
        self.assertIsNotNone(mm._preload_queue, "the warm-up must wait, not end")
        mm.PRELOAD_ONLY_FROM_HOST_LOOP = False
        QtWait.until(lambda: hud.is_initialized, "the warm-up never resumed")

    def test_the_warm_up_waits_while_the_pointer_moves(self):
        """A warm blocks the host (up to seconds in Maya 2025), so it runs only
        while the pointer rests: one landing as the user heads for a key_show
        press held that press up (live: the marking menu "does not start
        smoothly")."""
        mm = self._make_mm("t_preload_pointer")
        hud = self._add_page(mm, "hud#startmenu")
        steps = itertools.count()
        moving = staticmethod(lambda *_a: QtCore.QPoint(next(steps), 0))

        with mock.patch.object(QtGui.QCursor, "pos", moving):
            mm.preload_menus()
            for _ in range(5):
                self._drain_qt_events()
            self.assertFalse(hud.is_initialized, "a page was built mid-move")
            self.assertIsNotNone(mm._preload_queue, "the warm-up must wait, not end")
        QtWait.until(
            lambda: hud.is_initialized,
            "the warm-up never resumed once the pointer rested",
            timeout_ms=5000,
        )

    def test_a_key_press_handled_inside_a_warm_up_still_shows_the_menu(self):
        """A page whose init pumps the event loop can hand a pending key_show
        press to the activation mid-warm, while the overlay is presented
        off-screen: the menu must still show once the warm-up returns.

        Live (Maya): the first key_show presses "don't launch well" -- a press
        landing in a native-menu warm-up ran inside it, showed nothing, and the
        warm-up then hid the overlay under the held key.
        """
        mm = self._make_mm("t_preload_reentrant")
        hud = self._add_page(mm, "hud#startmenu")
        mm.preload_menus(names=["hud#startmenu"], defer=False)
        central = _make_central()
        central.layout().addWidget(_PumpsOnFirstShow())
        self.track_widget(
            mm.sb.add_ui("main#startmenu", widget=central, tags={"startmenu"})
        )

        QtCore.QTimer.singleShot(0, lambda: mm._on_activation_press(QtCore.Qt.NoButton))
        mm.preload_menus(names=["main#startmenu"], defer=False)
        self._drain_qt_events()

        self.assertTrue(mm.isVisible(), "the press inside the warm-up showed nothing")
        self.assertIs(mm.currentWidget(), hud)
        self.assertTrue(hud.isVisible())

    def test_preload_defers_while_gesture_live(self):
        """A live gesture owns the overlay — the deferred warm-up must wait
        rather than hide/re-show it out from under the user."""
        mm = self._make_mm("t_preload_gesture")
        hud = self._add_page(mm, "hud#startmenu")
        self._add_page(mm, "main#startmenu")

        mm._activation_key_held = True  # gesture in progress
        mm.preload_menus()
        self._drain_qt_events()
        self.assertFalse(
            hud.is_initialized,
            "warm-up must not run mid-gesture",
        )

        # Gesture over: the retry path may continue warming.
        mm._activation_key_held = False
        mm._preload_next()
        self._drain_qt_events()
        self.assertTrue(hud.is_initialized)


class TestSubmenuPreload(_PreloadCase):
    """Preload also warms the submenus a warmed page's nav buttons open.

    Live report (Maya): preload "isn't really very effective where it
    matters". Warming only the binding targets left every submenu cold, so the
    first hover into each paid that page's whole init inside the gesture
    (0.3-2.6 s apiece in Maya 2025). The warm-up now follows what hover opens
    (``MenuButton.submenu_name()``), and only to a stacked page a hover can
    reach: a standalone tool stays lazy, and a launcher the context hides
    opens nothing.
    """

    def setUp(self):
        super().setUp()
        self._tmp = ptk.TempArtifacts("uitk_test_preload_submenus", policy="scoped")
        self.ui_dir = self._tmp.dir_path()
        for stem in ("sub#submenu", "hidden#submenu", "tool"):
            write_ui_file(
                os.path.join(self.ui_dir, f"{stem}.ui"), stem.replace("#", "_")
            )

    def tearDown(self):
        super().tearDown()
        self._tmp.cleanup()

    def _make_start(self, mm: MarkingMenu) -> QtWidgets.QWidget:
        """``hud#startmenu`` with three launchers: a submenu, a standalone
        tool, and a submenu launcher the context hides (``requires``)."""
        central = _make_central()
        layout = central.layout()
        for name, target in (("i001", "sub"), ("i002", "tool"), ("i003", "hidden")):
            # Named, as every .ui widget is: registration (and with it the
            # visibility policy) skips an unnamed child.
            button = MenuButton(target=target)
            button.setObjectName(name)
            if target == "hidden":
                button.setProperty("requires", "another_host")
            layout.addWidget(button)
        page = mm.sb.add_ui("hud#startmenu", widget=central, tags={"startmenu"})
        self.track_widget(page)
        return page

    def _assert_warmed_only_the_hover_target(self, mm: MarkingMenu) -> None:
        sub = mm.sb.loaded_ui.peek("sub#submenu")
        self.assertIsNotNone(sub, "the submenu a hover opens was never loaded")
        self.assertTrue(sub.is_initialized, "the submenu a hover opens was left cold")
        self.assertFalse(sub.isVisible(), "a warmed submenu must end hidden")
        self.assertIsNone(
            mm.sb.loaded_ui.peek("tool"), "a standalone tool must stay lazy"
        )
        self.assertIsNone(
            mm.sb.loaded_ui.peek("hidden#submenu"),
            "a launcher the context hides opens nothing; its submenu stays cold",
        )
        self.assertTrue(mm.isHidden(), "warming must never present the overlay")

    def test_preload_warms_the_submenus_a_hover_opens(self):
        mm = self._make_mm("t_preload_sub", ui_source=self.ui_dir)
        self._make_start(mm)

        mm.preload_menus(defer=False)

        self._assert_warmed_only_the_hover_target(mm)

    def test_deferred_preload_reaches_the_submenus(self):
        mm = self._make_mm("t_preload_sub_deferred", ui_source=self.ui_dir)
        self._make_start(mm)

        mm.preload_menus()
        QtWait.until(
            lambda: mm._preload_queue is None, "the deferred warm-up never finished"
        )

        self._assert_warmed_only_the_hover_target(mm)

    def test_an_excluded_submenu_stays_cold(self):
        """``PRELOAD_EXCLUDE`` keeps a page out of the walk: a host whose
        submenu init has side effects (a native menu that loads a plugin)
        lets the first hover pay it instead."""
        mm = self._make_mm("t_preload_sub_excluded", ui_source=self.ui_dir)
        mm.PRELOAD_EXCLUDE = ("sub#*",)
        start = self._make_start(mm)

        mm.preload_menus(defer=False)

        self.assertTrue(start.is_initialized, "the binding target still warms")
        self.assertIsNone(
            mm.sb.loaded_ui.peek("sub#submenu"), "an excluded submenu must stay cold"
        )

    def test_a_page_already_shown_still_leads_to_its_submenus(self):
        """A start menu a gesture initialized before the warm-up reached it
        is skipped as a page, but its submenus are still warmed."""
        mm = self._make_mm("t_preload_sub_shown", ui_source=self.ui_dir)
        start = self._make_start(mm)
        mm.show("hud#startmenu")
        mm.hide()
        self.assertTrue(start.is_initialized, "precondition: the gesture warmed it")

        mm.preload_menus(defer=False)

        self._assert_warmed_only_the_hover_target(mm)


class TestColdFirstShowPositioning(_PreloadCase):
    """Without preload, the first activation must still end centered on its
    anchor — the first-show init that lands at the present must not leave the
    page positioned against pre-init geometry."""

    def _shown_center_offset(self, mm: MarkingMenu, page: QtWidgets.QWidget) -> int:
        shown = mm.show("hud#startmenu")
        self.assertIs(shown, page)
        self.assertTrue(mm.isVisible())
        self.assertTrue(
            page.is_initialized,
            "the present must have delivered the page's first showEvent",
        )
        # Compare against the gesture origin the code itself recorded — the
        # point the directional flick is measured from, and therefore the
        # invariant that matters. (Reading QCursor.pos() here instead is
        # flaky on a live desktop QPA: the developer's real mouse can move
        # between this read and the one inside _show_marking_menu.)
        anchor = mm.overlay.path.start_pos
        self.assertIsNotNone(anchor, "a startmenu show must start a gesture")
        center = page.mapToGlobal(page.rect().center())
        return (center - anchor).manhattanLength()

    def test_first_activation_centers_on_settled_geometry(self):
        mm = self._make_mm("t_cold_center")
        page = self._add_page(mm, "hud#startmenu")
        self.assertFalse(page.is_initialized, "precondition: cold page")

        offset = self._shown_center_offset(mm, page)
        self.assertLessEqual(
            offset,
            2,
            f"first activation ended {offset}px off its anchor — the page was "
            "centered against pre-first-show geometry and never re-centered "
            "after the present settled it (the 'first press feels "
            "uninitialized' report)",
        )

    def test_second_activation_matches_first(self):
        """The complaint is first-vs-second inconsistency; both must center
        the same way."""
        mm = self._make_mm("t_cold_parity")
        page = self._add_page(mm, "hud#startmenu")

        first = self._shown_center_offset(mm, page)
        mm.hide()
        self._drain_qt_events()
        second = self._shown_center_offset(mm, page)
        self.assertLessEqual(
            abs(first - second),
            2,
            f"first activation positioned {first}px off-anchor vs {second}px "
            "on the second — the two presses must behave identically",
        )

    def test_preloaded_page_first_activation_centers(self):
        """End-to-end: with scoped preloading on, the first activation is
        just another reopen — centered, no cold path at all."""
        mm = self._make_mm("t_warm_center")
        page = self._add_page(mm, "hud#startmenu")
        mm.preload_menus(defer=False)
        self.assertTrue(page.is_initialized)

        offset = self._shown_center_offset(mm, page)
        self.assertLessEqual(offset, 2)


if __name__ == "__main__":
    unittest.main()
