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
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase
from uitk.widgets.marking_menu._marking_menu import MarkingMenu


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
            "preload=True must warm the binding targets once the event loop "
            "spins",
        )
        self.assertTrue(mm.isHidden())

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
