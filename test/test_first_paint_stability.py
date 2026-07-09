# !/usr/bin/python
# coding=utf-8
"""First-paint stability — init-time flash regression suite.

uitk's anti-flash doctrine: all visual state is FINAL by the time show()
returns; anything corrected on a later tick painted the un-final state first
(the "menus/option-boxes flash on init" report). Each test here pins one
flash vector using the conftest harness (`assert_stable_after_show`) and the
property-selector QSS reproducer (`FIRST_PAINT_QSS`) — dynamic-property rules
don't re-evaluate without an unpolish/polish cycle, so metrics measured after
a `setProperty("class", ...)` stamp are stale until repolish (the mechanism
behind the "measured pre-polish, corrected on show" class of flashes;
validated by spike 2026-07-09, see CHANGELOG).
"""
import unittest

from qtpy import QtCore, QtWidgets

from conftest import (
    FIRST_PAINT_QSS,
    QtBaseTestCase,
    assert_stable_after_show,
    visual_state_snapshot,
    diff_visual_state,
)


class _StaleStyledButton(QtWidgets.QPushButton):
    """A wrapped-widget stand-in whose QSS metrics are STALE at wrap time.

    The parent window carries FIRST_PAINT_QSS; stamping class="tight" after
    construction leaves the 80px type-rule metrics in effect until a
    repolish — exactly the state a themed DCC widget is in when the
    option-box wrap measures it.
    """


def _make_stale_button(parent, text="Xy"):
    btn = _StaleStyledButton(text, parent)
    btn.setObjectName("tb000")
    # Polish FIRST (a first-time polish resolves current properties, so a
    # never-polished widget can't go stale) — real DCC widgets are polished
    # long before the wrap runs. THEN stamp the property: the [class="tight"]
    # rule now stays un-applied until an unpolish/polish cycle.
    btn.ensurePolished()
    btn.setProperty("class", "tight")
    return btn


class TestOptionBoxWrapFirstMeasurementFinal(QtBaseTestCase):
    """Phase 2: the wrap must measure post-repolish so wrap-time geometry is
    final — the showEvent refit then has nothing to correct on-screen."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()
        self.window = QtWidgets.QWidget()
        self.window.setStyleSheet(FIRST_PAINT_QSS)
        self.window.resize(600, 400)
        self.track_widget(self.window)

    def _wrap_absolute(self):
        """Wrap a stale-styled button in the absolute-positioned (overlay)
        shape: parented, NOT in a layout."""
        from uitk.widgets.optionBox._optionBox import OptionBox

        btn = _make_stale_button(self.window)
        btn.setGeometry(200, 150, 90, 24)  # authored geometry
        box = OptionBox(show_clear=False)
        container = box.wrap(btn)
        return btn, box, container

    def test_wrap_measures_repolished_metrics(self):
        """The wrapped widget's stale 80px type-rule floor must be collapsed
        (property rule applied) BEFORE the wrap sizes the container."""
        btn, box, container = self._wrap_absolute()
        # Post-fix: wrap repolished the tree, so the button's minimumSizeHint
        # reflects the [class="tight"] rule (8px floor), not the 80px one.
        self.assertLess(
            btn.minimumSizeHint().width(),
            80,
            "wrap measured the STALE type-rule floor — property-selector QSS "
            "was not repolished before sizing (the pre-polish inflation).",
        )

    def test_overlay_container_stable_after_show(self):
        """End-to-end: no visible geometry correction after show() returns."""
        btn, box, container = self._wrap_absolute()
        assert_stable_after_show(self, self.window)

    def test_refit_not_scheduled_when_geometry_already_final(self):
        """Routine case post-fix: the showEvent safety-net refit must not even
        schedule (zero deferred timers, zero post-show adjust work)."""
        btn, box, container = self._wrap_absolute()
        calls = []
        orig = type(container)._adjust_to_content

        def probe(self_c):
            calls.append(self_c.isVisible())
            return orig(self_c)

        type(container)._adjust_to_content = probe
        try:
            self.window.show()
            post_show_baseline = len(calls)
            self._drain_qt_events()
        finally:
            type(container)._adjust_to_content = orig
        self.assertEqual(
            len(calls),
            post_show_baseline,
            "the showEvent refit ran post-show in the routine case — it must "
            "be a conditional safety net, not a scheduled correction.",
        )

    def test_refit_safety_net_still_fires_when_inflated(self):
        """The refit must survive as a safety net: a genuinely wrong-size
        container (manually inflated, the TestOptionBoxOverlayRefit contract)
        is still corrected."""
        btn, box, container = self._wrap_absolute()
        container.resize(container.width() + 220, container.height())
        self.window.show()
        self._drain_qt_events()
        self.assertLess(
            container.width(),
            220 + 90,
            "manually inflated container was never re-fit — the safety net "
            "died with the flash fix.",
        )


class TestChromeInitialStateFinal(QtBaseTestCase):
    """Phase 4: option/chrome widgets must paint their FINAL initial state —
    no show-then-hide (ClearOption), no post-paint icon swap (PinValues),
    no post-paint header mutation (menu-button sync / auto-hide)."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()
        self.window = QtWidgets.QWidget()
        self.window.resize(500, 300)
        self.track_widget(self.window)
        self.layout = QtWidgets.QVBoxLayout(self.window)

    def _find_clear_button(self):
        """The clear button by ButtonOption's naming convention
        (<WrappedType>_ClearOption)."""
        for b in self.window.findChildren(QtWidgets.QPushButton):
            if b.objectName().endswith("_ClearOption"):
                return b
        self.fail("no ClearOption button found in the wrapped tree")

    def test_clear_button_hidden_at_show_return_on_empty_field(self):
        """An EMPTY field's clear button must never paint visible-then-hide."""
        from uitk.widgets.optionBox._optionBox import OptionBox

        field = QtWidgets.QLineEdit(self.window)  # empty
        self.layout.addWidget(field)
        box = OptionBox(show_clear=True)
        box.wrap(field)

        self.window.show()
        clear_btn = self._find_clear_button()
        self.assertFalse(
            clear_btn.isVisible(),
            "clear button visible at show-return on an EMPTY field — it "
            "paints, then the deferred update hides it (the flash).",
        )
        # And with text, it must be visible at show-return + stay stable.
        field.setText("abc")
        self._drain_qt_events()
        self.assertTrue(clear_btn.isVisible(), "late setText must still show it")

    def test_clear_button_visible_at_show_return_with_text(self):
        from uitk.widgets.optionBox._optionBox import OptionBox

        field = QtWidgets.QLineEdit(self.window)
        field.setText("preset")
        self.layout.addWidget(field)
        box = OptionBox(show_clear=True)
        box.wrap(field)

        self.window.show()
        clear_btn = self._find_clear_button()
        self.assertTrue(clear_btn.isVisible())
        before = visual_state_snapshot(self.window)
        self._drain_qt_events()
        delta = diff_visual_state(before, visual_state_snapshot(self.window))
        self.assertEqual(delta, [], f"post-show mutation: {delta}")

    def test_pin_icon_has_no_post_show_deferred_update(self):
        """The pin button's icon must be correct at creation — a deferred
        initial update lands post-paint (icon flicker). Value changes still
        update via the signal connections."""
        from uitk.widgets.optionBox._optionBox import OptionBox
        from uitk.widgets.optionBox.options.pin_values import PinValuesOption

        calls = []
        orig = PinValuesOption._update_button_icon

        def probe(self_o, *a):
            calls.append(a)
            return orig(self_o, *a)

        # Patch BEFORE the wrap: the deferred create-time update captures the
        # bound method at schedule time, so a later patch would miss it.
        PinValuesOption._update_button_icon = probe
        try:
            field = QtWidgets.QSpinBox(self.window)
            self.layout.addWidget(field)
            box = OptionBox(show_clear=False)
            option = PinValuesOption(field)
            box.add_option(option)
            box.wrap(field)

            self.window.show()
            at_show = len(calls)
            self._drain_qt_events()
            post_show = len(calls) - at_show
        finally:
            PinValuesOption._update_button_icon = orig
        self.assertEqual(
            post_show,
            0,
            "pin icon updated on a post-paint tick (the icon flicker) — the "
            "initial state must be set synchronously at creation.",
        )

    def test_header_menu_button_final_at_show_return(self):
        """A menu-configured header over an EMPTY menu must have its menu
        button already hidden at show-return (not hidden one tick later)."""
        from uitk.widgets.header import Header

        header = Header(self.window, config_buttons=["menu"])
        self.layout.addWidget(header)

        self.window.show()
        menu_btn = header.buttons.get("menu")
        self.assertIsNotNone(menu_btn)
        self.assertFalse(
            menu_btn.isVisible(),
            "menu button visible at show-return over an empty menu — the "
            "deferred sync hides it post-paint (the flash).",
        )
        before = visual_state_snapshot(self.window)
        self._drain_qt_events()
        delta = diff_visual_state(before, visual_state_snapshot(self.window))
        self.assertEqual(delta, [], f"post-show header mutation: {delta}")


class TestNoStrayPopupsAndVisibleWrapSuppression(QtBaseTestCase):
    """Phase 5: no real popup may appear during add(); a wrap on a VISIBLE
    window suppresses updates window-wide (one repaint, no flicker)."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()

    def test_action_widget_realization_shows_no_menu_at_all(self):
        """add(QAction/QWidgetAction) must not show ANY QMenu — pre-fix a
        temporary QMenu was really shown (+ processEvents) to realize the
        action's widget, flashing an empty popup during add(). (The
        realization API, QMenu.widgetForAction, is also gone from newer
        PySide6 — the old path hard-crashed there.)"""
        from uitk.widgets.menu import Menu

        shown_menus = []

        class _Spy(QtCore.QObject):
            def eventFilter(self, obj, event):
                if event.type() == QtCore.QEvent.Show and isinstance(
                    obj, QtWidgets.QMenu
                ):
                    shown_menus.append(obj)
                return False

        spy = _Spy()
        app = QtWidgets.QApplication.instance()
        app.installEventFilter(spy)
        try:
            menu = Menu()
            self.track_widget(menu)
            payload = QtWidgets.QLabel("payload")
            waction = QtWidgets.QWidgetAction(menu)
            waction.setDefaultWidget(payload)
            got = menu.add(waction)

            plain = QtWidgets.QAction("plain", menu)
            got_plain = menu.add(plain)
        finally:
            app.removeEventFilter(spy)

        self.assertEqual(
            shown_menus, [], "a QMenu was shown during add() — the stray popup"
        )
        self.assertIs(got, payload, "QWidgetAction's defaultWidget not used")
        self.assertIsInstance(
            got_plain, QtWidgets.QToolButton, "plain QAction needs a carrier"
        )
        self.assertIs(got_plain.defaultAction(), plain)

    def test_visible_window_wrap_suppresses_window_updates(self):
        """Slow-path shape: wrapping inside an already-visible window must
        hold updatesEnabled(False) on the WINDOW for the reparent swap."""
        from uitk.widgets.optionBox._optionBox import OptionBox

        window = QtWidgets.QWidget()
        self.track_widget(window)
        outer = QtWidgets.QVBoxLayout(window)
        panel = QtWidgets.QWidget(window)  # nested: parent is not window
        inner = QtWidgets.QVBoxLayout(panel)
        outer.addWidget(panel)
        field = QtWidgets.QLineEdit(panel)
        inner.addWidget(field)
        window.show()
        self._drain_qt_events()
        self.assertTrue(window.isVisible())

        states = []
        box = OptionBox(show_clear=False)
        orig_apply = OptionBox._apply_border_styling

        def probe(self_b, *a, **k):
            states.append(window.updatesEnabled())  # mid-wrap sample
            return orig_apply(self_b, *a, **k)

        OptionBox._apply_border_styling = probe
        try:
            box.wrap(field)
        finally:
            OptionBox._apply_border_styling = orig_apply

        self.assertEqual(
            states,
            [False],
            "window-level updates were NOT suppressed during a visible-window "
            "wrap — the reparent swap repaints mid-flight (the flicker).",
        )
        self.assertTrue(
            window.updatesEnabled(), "suppression must be restored after wrap"
        )


class TestLayoutManagedWrapUnaffected(QtBaseTestCase):
    """Layout-managed (docked-panel) wraps never had the refit path; the
    repolish must not perturb them either."""

    def setUp(self):
        super().setUp()
        self._drain_qt_events()
        self.window = QtWidgets.QWidget()
        self.window.setStyleSheet(FIRST_PAINT_QSS)
        self.track_widget(self.window)
        self.layout = QtWidgets.QVBoxLayout(self.window)

    def test_layout_wrap_stable_after_show(self):
        from uitk.widgets.optionBox._optionBox import OptionBox

        btn = _make_stale_button(self.window)
        self.layout.addWidget(btn)
        box = OptionBox(show_clear=False)
        box.wrap(btn)
        # Realistic window size: a content-sized (~33px) top-level would be
        # force-resized by the OS to its minimum captioned-window width right
        # after show — an OS constraint, not an init flash.
        self.window.resize(400, 120)
        assert_stable_after_show(self, self.window)


if __name__ == "__main__":
    unittest.main()
