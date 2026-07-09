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
        assert_stable_after_show(self, self.window)


if __name__ == "__main__":
    unittest.main()
