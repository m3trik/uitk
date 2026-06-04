# !/usr/bin/python
# coding=utf-8
"""Regression tests for the MainWindow dynamic-resize API.

Covers:
- ``adjust_height_by`` applies a signed delta, preserves width, clamps to min.
- ``fit_height_to_content`` snaps to layout's natural content height.
- ``CollapsableGroup`` delegates its window resize through the central API
  (verified via a stubbed ``adjust_height_by`` recorder).
- End-to-end shrink/grow: collapsing a CollapsableGroup in a tentacle-style
  layout (multiple groups + trailing vertical spacer + footer) must actually
  decrease ``window.height()``; expanding must restore it.
"""
import itertools
import unittest

from qtpy import QtCore, QtWidgets

from conftest import QtBaseTestCase

from uitk.widgets.mainWindow import MainWindow
from uitk.widgets.collapsableGroup import CollapsableGroup


class _BareSwitchboard:
    """Minimal stand-in so MainWindow's __init__ can complete without uitk.Switchboard."""

    def convert_to_legal_name(self, name):
        return name

    def get_base_name(self, name):
        return name

    def has_tags(self, *_a, **_k):
        return False

    def get_slots_instance(self, *_a, **_k):
        return None

    def center_widget(self, *_a, **_k):
        return None


def _build_window(content_widget):
    """Construct a MainWindow with content_widget centered, return it."""
    win = MainWindow(
        name="test_resize_window",
        switchboard_instance=_BareSwitchboard(),
        central_widget=content_widget,
        restore_window_size=False,
        ensure_on_screen=False,
    )
    return win


class TestAdjustHeightBy(QtBaseTestCase):
    """Signed-delta resize."""

    def test_zero_delta_is_a_noop(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win = self.track_widget(_build_window(central))
        win.resize(300, 400)
        win.adjust_height_by(0)
        self.assertEqual(win.height(), 400)
        self.assertEqual(win.width(), 300)

    def test_positive_delta_grows_window_preserving_width(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win = self.track_widget(_build_window(central))
        win.resize(300, 400)
        win.adjust_height_by(50)
        self.assertEqual(win.height(), 450)
        self.assertEqual(win.width(), 300)

    def test_negative_delta_clamped_to_minimum_size_hint(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        # Force a known minimum content size
        spacer = QtWidgets.QLabel("x" * 20)
        spacer.setMinimumHeight(120)
        layout.addWidget(spacer)
        win = self.track_widget(_build_window(central))
        win.show()
        win.resize(300, 400)
        QtWidgets.QApplication.processEvents()

        win.adjust_height_by(-1000)  # would go negative
        self.assertGreaterEqual(win.height(), win.minimumSizeHint().height())
        self.assertEqual(win.width(), 300)


class TestFitHeightToContent(QtBaseTestCase):
    """Snap-to-content resize."""

    def test_fit_collapses_to_minimum_size_hint(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        label = QtWidgets.QLabel("hi")
        label.setFixedHeight(30)
        layout.addWidget(label)
        win = self.track_widget(_build_window(central))
        win.show()
        win.resize(400, 800)  # user-stretched
        QtWidgets.QApplication.processEvents()

        win.fit_height_to_content()
        # Width preserved; height snapped near the minimum hint.
        self.assertEqual(win.width(), 400)
        self.assertLess(win.height(), 800)
        self.assertGreaterEqual(win.height(), win.minimumSizeHint().height() - 1)


class TestCollapsableGroupDelegatesToMainWindow(QtBaseTestCase):
    """CollapsableGroup must hand the resize off to MainWindow.adjust_height_by."""

    def test_toggle_invokes_adjust_height_by(self):
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        group = CollapsableGroup("Test")
        group.restore_state = False
        group.setLayout(QtWidgets.QVBoxLayout())
        group.addWidget(QtWidgets.QLabel("inner"))
        group.addWidget(QtWidgets.QLabel("inner2"))
        layout.addWidget(group)
        win = self.track_widget(_build_window(central))
        win.show()
        QtWidgets.QApplication.processEvents()

        calls = []
        win.adjust_height_by = lambda d: calls.append(d)

        group.toggle_expand(False)  # collapse
        self.assertTrue(
            calls and calls[-1] < 0,
            f"Expected negative delta on collapse, got {calls!r}",
        )

        group.toggle_expand(True)  # expand
        self.assertTrue(
            calls and calls[-1] > 0,
            f"Expected positive delta on expand, got {calls!r}",
        )


# Per-build counter ensures unique CollapsableGroup objectNames across test
# methods. CollapsableGroup writes its checked-state to a shared QSettings
# store keyed by objectName; reusing names lets one test's persisted state
# leak into the next.
_group_name_counter = itertools.count(1)


def _build_tentacle_like_central(group_specs):
    """Build a central widget matching tentacle's panel layout.

    Structure mirrors ``transform_ui.py`` and other tentacle panels:

        central_widget (minimumSize 200x0)
        └─ verticalLayout_2 (margins 2, spacing 2)
           └─ verticalLayout (spacing 0)        ← nested inner layout
              ├─ Header (QLabel, h=19)
              ├─ CollapsableGroup * N
              ├─ QSpacerItem(0, 10, Minimum, Expanding)
              └─ Footer (QLabel, h=19)

    Each call uses a unique objectName prefix so QSettings entries written
    by CollapsableGroup (in case restore_state default leaks before the test
    flips it off) can't bleed between tests.

    Parameters:
        group_specs: list of (objectName, [child_heights]) tuples — each tuple
            yields one CollapsableGroup with that name and child rows of the
            given heights (matching tentacle's typical 19px button rows).

    Returns:
        (central_widget, list_of_groups)
    """
    suffix = f"_t{next(_group_name_counter)}"
    central = QtWidgets.QWidget()
    central.setMinimumSize(QtCore.QSize(200, 0))

    outer = QtWidgets.QVBoxLayout(central)
    outer.setContentsMargins(2, 2, 2, 2)
    outer.setSpacing(2)

    inner = QtWidgets.QVBoxLayout()
    inner.setSpacing(0)

    header = QtWidgets.QLabel("HEADER")
    header.setObjectName("header")
    header.setMinimumSize(QtCore.QSize(0, 19))
    inner.addWidget(header)

    groups = []
    for name, child_heights in group_specs:
        # Disable persistence BEFORE construction by using a kwarg path that
        # set_attributes will honor in __init__, so even the deferred
        # _enforce_state QTimer can't read stale QSettings for this name.
        g = CollapsableGroup(name + suffix, restore_state=False)
        g.setObjectName(name + suffix)
        g.setMinimumSize(QtCore.QSize(125, 0))
        g.restore_state = False
        g_layout = QtWidgets.QVBoxLayout(g)
        g_layout.setSpacing(1)
        g_layout.setContentsMargins(0, 0, 0, 0)
        for h in child_heights:
            btn = QtWidgets.QPushButton(f"{name}_row")
            btn.setMinimumSize(QtCore.QSize(0, h))
            btn.setMaximumSize(QtCore.QSize(16777215, h))
            g_layout.addWidget(btn)
        inner.addWidget(g)
        groups.append(g)

    inner.addSpacerItem(
        QtWidgets.QSpacerItem(
            0, 10,
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Expanding,
        )
    )

    footer = QtWidgets.QLabel("footer")
    footer.setObjectName("footer")
    footer.setMinimumSize(QtCore.QSize(0, 19))
    footer.setMaximumSize(QtCore.QSize(16777215, 19))
    inner.addWidget(footer)

    outer.addLayout(inner)
    return central, groups


class TestCollapseShrinksWindowEndToEnd(QtBaseTestCase):
    """The window's height must actually change when groups collapse/expand.

    These tests exercise the full path (no stubbing) in a layout that mirrors
    tentacle's panel structure: nested QVBoxLayouts, multiple CollapsableGroups,
    a trailing vertical spacer with Expanding policy, and a Footer. The spacer
    is the interesting bit — it absorbs freed vertical space within the
    central widget, which is exactly the configuration that could mask a
    failure to resize the *window*.
    """

    def _flush(self):
        """Drain pending events so layout + resize calls settle."""
        for _ in range(3):
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.AllEvents, 50
            )

    def test_collapse_shrinks_window_height(self):
        central, groups = _build_tentacle_like_central([
            ("transform", [19] * 6),
            ("align", [19]),
            ("constraints", [19, 19]),
        ])
        win = self.track_widget(_build_window(central))
        win.show()
        self._flush()

        target = groups[0]
        h_before = win.height()
        g_before = target.height()
        target.toggle_expand(False)
        self._flush()
        h_after = win.height()

        # The window must actually shrink. If adjust_height_by clamps the
        # resize because minimumSizeHint is computed before layouts settle,
        # h_after == h_before — the reported bug.
        self.assertLess(
            h_after, h_before,
            f"Collapse should shrink window: {h_before}→{h_after} "
            f"(group {g_before}→{target.height()})",
        )

        # Sanity: the shrinkage should be at least most of the group's height
        # delta. Allow a few px slack for spacer/margin rounding.
        group_delta = g_before - target.height()
        window_delta = h_before - h_after
        self.assertGreaterEqual(
            window_delta, group_delta - 4,
            f"Window shrunk too little: windowΔ={window_delta}, "
            f"groupΔ={group_delta}",
        )

    def test_collapse_then_expand_restores_window_height(self):
        central, groups = _build_tentacle_like_central([
            ("transform", [19] * 6),
            ("align", [19]),
            ("constraints", [19, 19]),
        ])
        win = self.track_widget(_build_window(central))
        win.show()
        self._flush()

        target = groups[0]
        h_initial = win.height()

        target.toggle_expand(False)
        self._flush()
        target.toggle_expand(True)
        self._flush()

        # A full collapse+expand cycle must return to the same window height.
        # Drift here would mean either:
        #  - _expanded_height isn't being captured correctly
        #  - sizeHint fallback is overpredicting
        #  - adjust_height_by is computing deltas off a stale baseline
        self.assertEqual(
            win.height(), h_initial,
            f"Expand should restore height: initial={h_initial}, "
            f"after-cycle={win.height()}",
        )

    def test_multiple_toggle_cycles_no_drift(self):
        central, groups = _build_tentacle_like_central([
            ("g0", [19] * 4),
            ("g1", [19] * 3),
        ])
        win = self.track_widget(_build_window(central))
        win.show()
        self._flush()

        target = groups[0]
        baseline = win.height()
        for _ in range(5):
            target.toggle_expand(False)
            self._flush()
            target.toggle_expand(True)
            self._flush()

        self.assertEqual(
            win.height(), baseline,
            f"Repeated cycles must not drift: baseline={baseline}, "
            f"final={win.height()}",
        )

    def test_collapse_shrinks_when_window_pre_stretched(self):
        """Collapse must shrink the window even when it was pre-stretched.

        When the user (or a restored geometry) has stretched the window past
        its natural sizeHint, the trailing Expanding spacer absorbs the slack
        and the central widget's *visible* layout fits comfortably. Collapse
        must still produce a measurable shrink — the freed group pixels
        cannot just be absorbed by the spacer or the window will never get
        smaller. Width is preserved.
        """
        central, groups = _build_tentacle_like_central([
            ("transform", [19] * 6),
            ("align", [19]),
        ])
        win = self.track_widget(_build_window(central))
        win.show()
        self._flush()

        # Stretch beyond natural — the Expanding spacer will absorb it.
        win.resize(300, max(win.height() + 200, 600))
        self._flush()

        target = groups[0]
        h_before = win.height()
        g_before = target.height()
        target.toggle_expand(False)
        self._flush()

        self.assertLess(
            win.height(), h_before,
            f"Pre-stretched window must still shrink on collapse: "
            f"{h_before}→{win.height()}",
        )
        # Width preserved
        self.assertEqual(win.width(), 300)
        # Shrink should track the group's collapse delta (modulo a few px
        # for spacer/margin rounding).
        group_delta = g_before - target.height()
        window_delta = h_before - win.height()
        self.assertGreaterEqual(
            window_delta, group_delta - 4,
            f"Pre-stretched window shrunk too little: windowΔ={window_delta}, "
            f"groupΔ={group_delta}",
        )

    def test_collapsing_one_group_does_not_resize_others(self):
        """A toggle on group A should not change group B's height."""
        central, groups = _build_tentacle_like_central([
            ("transform", [19] * 6),
            ("align", [19, 19, 19]),
        ])
        win = self.track_widget(_build_window(central))
        win.show()
        self._flush()

        other_before = groups[1].height()
        groups[0].toggle_expand(False)
        self._flush()
        other_mid = groups[1].height()
        groups[0].toggle_expand(True)
        self._flush()
        other_after = groups[1].height()

        self.assertEqual(other_before, other_mid)
        self.assertEqual(other_before, other_after)


class TestFitToContentOnShow(QtBaseTestCase):
    """First-show fit that removes the deadspace gap above a footer/spacer.

    The wiring lives in ``MainWindow.showEvent``: on the first show it calls
    ``fit_height_to_content`` unless a saved window size was restored (which the
    user set intentionally) or the feature was opted out via the ctor flag.
    """

    def _spy_window(self, central, **kwargs):
        """Build a window whose ``fit_height_to_content`` records its calls."""
        win = self.track_widget(
            MainWindow(
                name="test_fit_on_show",
                switchboard_instance=_BareSwitchboard(),
                central_widget=central,
                ensure_on_screen=False,
                **kwargs,
            )
        )
        calls = []
        win.fit_height_to_content = lambda: calls.append(1)
        return win, calls

    def test_fit_runs_on_first_show_by_default(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win, calls = self._spy_window(central, restore_window_size=False)
        win.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(calls, [1], "Fit should run exactly once on first show")

    def test_fit_skipped_when_disabled(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win, calls = self._spy_window(
            central, restore_window_size=False, fit_to_content_on_show=False
        )
        win.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(calls, [], "Fit must not run when opted out")

    def test_fit_skipped_when_saved_geometry_restored(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win, calls = self._spy_window(central, restore_window_size=True)
        # Simulate a successfully restored user size.
        win.restore_window_geometry = lambda: True
        win.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(
            calls, [], "Fit must not clobber a restored user-set size"
        )

    def test_fit_runs_only_on_first_show(self):
        central = QtWidgets.QWidget()
        QtWidgets.QVBoxLayout(central)
        win, calls = self._spy_window(central, restore_window_size=False)
        win.show()
        QtWidgets.QApplication.processEvents()
        win.hide()
        QtWidgets.QApplication.processEvents()
        win.show()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(calls, [1], "Fit is a first-show-only concern")

    def test_deadspace_collapsed_on_show(self):
        """End-to-end: a footer + trailing Expanding spacer leaves no gap.

        The real fit (not stubbed) must leave the shown window content-tight,
        i.e. its height equals the minimum size hint — the Expanding spacer
        that would otherwise pad the area above the footer is collapsed.
        """
        central, _groups = _build_tentacle_like_central([
            ("transform", [19] * 4),
            ("align", [19]),
        ])
        win = self.track_widget(_build_window(central))  # restore off, fit on
        win.show()
        for _ in range(3):
            QtWidgets.QApplication.processEvents()

        self.assertLessEqual(
            abs(win.height() - win.minimumSizeHint().height()), 2,
            f"Window should be content-tight on show (no deadspace): "
            f"height={win.height()}, minHint={win.minimumSizeHint().height()}",
        )


if __name__ == "__main__":
    unittest.main()
