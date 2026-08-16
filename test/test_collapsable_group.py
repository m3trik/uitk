# !/usr/bin/python
# coding=utf-8
"""Unit tests for the CollapsableGroup widget.

CollapsableGroup is a checkable QGroupBox whose title doubles as an
expand/collapse toggle. The checkbox indicator the style draws to the left of
the title is unwanted: it indents the title relative to a plain QGroupBox, and
the QSS ``::indicator { width:0; height:0 }`` rule doesn't fully remove it
(under QStyleSheetStyle it leaves a residual indent — the offset seen in
Blender). These tests pin the style-independent contract:

- the checkable indicator subcontrol is suppressed for painting, and
- the title aligns with a plain (non-checkable) QGroupBox,

while collapse-via-toggle keeps working.

Run standalone: python -m test.test_collapsable_group
"""

import unittest

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtGui, QtCore  # noqa: E402

from uitk.widgets.collapsableGroup import CollapsableGroup  # noqa: E402
from uitk.widgets.mixins.size_grip import SizeGripMixin  # noqa: E402


class TestCollapsableGroupIndicatorHidden(QtBaseTestCase):
    """The checkbox indicator is hidden and its reserved space reclaimed, so the
    title aligns with a plain QGroupBox regardless of the active Qt style."""

    def test_group_is_checkable_with_indicator_subcontrol(self):
        """Precondition: it IS a checkable group box, so the style reserves a
        ``SC_GroupBoxCheckBox`` subcontrol — there is something to hide."""
        g = self.track_widget(CollapsableGroup("My Group"))
        self.assertTrue(g.isCheckable())
        opt = QtWidgets.QStyleOptionGroupBox()
        g.initStyleOption(opt)
        self.assertTrue(
            bool(opt.subControls & QtWidgets.QStyle.SC_GroupBoxCheckBox),
            "A checkable QGroupBox must carry SC_GroupBoxCheckBox by default.",
        )

    def test_paint_option_drops_checkbox_subcontrol(self):
        """The option used for painting must not include the checkbox subcontrol
        — that is what stops the indicator from being drawn."""
        g = self.track_widget(CollapsableGroup("My Group"))
        self.assertFalse(
            bool(
                g._checkbox_suppressed_option().subControls
                & QtWidgets.QStyle.SC_GroupBoxCheckBox
            ),
            "paintEvent must drop SC_GroupBoxCheckBox so the indicator isn't drawn.",
        )

    def test_title_aligns_with_plain_groupbox(self):
        """With the checkbox suppressed, the title's left edge matches a plain
        QGroupBox's title (the checkbox no longer reserves space)."""
        g = self.track_widget(CollapsableGroup("My Group"))
        g.resize(200, 80)
        plain = self.track_widget(QtWidgets.QGroupBox("My Group"))
        plain.resize(200, 80)

        cc = QtWidgets.QStyle.CC_GroupBox
        sc_label = QtWidgets.QStyle.SC_GroupBoxLabel

        g_label = g.style().subControlRect(
            cc, g._checkbox_suppressed_option(), sc_label, g
        )
        p_opt = QtWidgets.QStyleOptionGroupBox()
        plain.initStyleOption(p_opt)
        p_label = plain.style().subControlRect(cc, p_opt, sc_label, plain)

        self.assertEqual(
            g_label.x(),
            p_label.x(),
            "CollapsableGroup title must align with a plain QGroupBox title.",
        )

    def test_paints_without_error(self):
        """The paintEvent override is a valid replacement (renders cleanly)."""
        g = self.track_widget(CollapsableGroup("My Group"))
        g.resize(200, 80)
        pixmap = QtGui.QPixmap(g.size())
        g.render(pixmap)  # drives paintEvent through the override

    def test_hiding_checkbox_keeps_collapse_working(self):
        """Suppressing the indicator is cosmetic — toggling still collapses and
        expands the content (the title remains the toggle)."""
        g = self.track_widget(CollapsableGroup("My Group"))
        child = QtWidgets.QLabel("content")
        g.addWidget(child)

        g.setChecked(False)  # collapse
        self.assertTrue(child.isHidden())
        g.setChecked(True)  # expand
        self.assertFalse(child.isHidden())


class TestCollapsedStatePersistenceScope(QtBaseTestCase):
    """Collapse state persists per hosting window, not globally.

    Group names repeat across forms by convention (every bridge panel has an
    ``output_grp``); an unscoped key would share one collapse state across
    every panel that reuses the name.
    """

    def _hosted_group(self, window_name):
        win = self.track_widget(QtWidgets.QMainWindow())
        win.setObjectName(window_name)
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        group = CollapsableGroup("Log")
        group.setObjectName("output_grp")
        group.addWidget(QtWidgets.QLabel("content"))
        lay.addWidget(group)
        win.setCentralWidget(central)
        self.addCleanup(lambda: group.settings.remove("CollapsableGroup"))
        return win, group

    def test_key_is_scoped_by_window_object_name(self):
        _win, group = self._hosted_group("panel_a")
        self.assertEqual(
            group._settings_key(),
            "CollapsableGroup/panel_a/output_grp/checked",
        )

    def test_unhosted_group_falls_back_to_legacy_key(self):
        group = self.track_widget(CollapsableGroup("Log"))
        group.setObjectName("output_grp")
        self.assertEqual(
            group._settings_key(), "CollapsableGroup/output_grp/checked"
        )

    def test_toggle_before_enforcement_does_not_persist(self):
        """A toggle that lands before the group is settled into its window
        resolves a DIFFERENT scope than the restore reads, so persisting it
        would strand a value nothing reads back."""
        group = self.track_widget(CollapsableGroup("Log"))
        group.setObjectName("output_grp")
        self.addCleanup(lambda: group.settings.remove("CollapsableGroup"))
        self.assertFalse(group._state_enforced, "precondition: not yet settled")

        group.setChecked(False)  # e.g. a .ui authoring checked=false

        self.assertIsNone(
            group.settings.value(group._settings_key()),
            "a pre-enforcement toggle must not write state",
        )

    def test_toggle_after_enforcement_persists(self):
        _win, group = self._hosted_group("panel_c")
        group._enforce_state()
        group.setChecked(False)
        self.assertEqual(group.settings.value(group._settings_key()), False)

    def test_same_named_groups_in_different_windows_do_not_share_state(self):
        _win_a, group_a = self._hosted_group("panel_a")
        _win_b, group_b = self._hosted_group("panel_b")
        # Settle first, as a shown panel does: only a post-enforcement toggle
        # is a user choice worth persisting.
        group_a._enforce_state()
        group_b._enforce_state()
        group_a.setChecked(False)  # collapse A → persists under panel_a only

        # Fresh instances restoring state: A's twin collapses, B's stays open.
        _win_a2, group_a2 = self._hosted_group("panel_a")
        _win_b2, group_b2 = self._hosted_group("panel_b")
        group_a2._enforce_state()
        group_b2._enforce_state()
        self.assertFalse(group_a2.isChecked())
        self.assertTrue(group_b2.isChecked())


class TestFallbackWindowResizeFloor(QtBaseTestCase):
    """``_fallback_window_resize`` (non-``MainWindow`` hosts) clamps to the
    content's REAL minimum, using the same rule ``MainWindow`` does.

    Qt's ``qSmartMinSize`` replaces a container's layout-computed minimum with
    any explicit ``setMinimumSize`` — even one SMALLER than the content needs —
    so a stale ``minimumSize`` drags the *window's* hint below the real content
    height, and a resize to that value packs fixed-height rows into overlap.
    ``MainWindow`` has always guarded this; the fallback used the bare window
    hint, so the two floors could diverge. Both now call
    ``SizeGripMixin.content_min_height``.
    """

    def _host(self):
        """Plain QMainWindow (no ``adjust_height_by``) with an under-reporting
        central: rows need 200px of content, the explicit minimum claims 10."""
        win = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for _ in range(5):
            row = QtWidgets.QLabel("row")
            row.setFixedHeight(40)  # 5 * 40 = 200px of incompressible content
            layout.addWidget(row)
        group = CollapsableGroup("Collapsible", restore_state=False)
        group.restore_state = False
        g_layout = QtWidgets.QVBoxLayout(group)
        g_layout.setContentsMargins(0, 0, 0, 0)
        body = QtWidgets.QLabel("body")
        body.setFixedHeight(300)
        g_layout.addWidget(body)
        layout.addWidget(group)
        central.setMinimumHeight(10)  # the stale/under-reporting explicit min
        win.setCentralWidget(central)
        win.show()
        QtWidgets.QApplication.processEvents()
        return win, central, group

    def test_host_under_reports_its_minimum(self):
        """Precondition: the explicit min really does drag the window hint below
        the central's own (layout-computed) minimum — else the test is vacuous."""
        win, central, _group = self._host()
        self.assertLess(
            win.minimumSizeHint().height(),
            central.minimumSizeHint().height(),
            "fixture no longer reproduces the under-reporting minimum",
        )
        self.assertFalse(
            hasattr(win, "adjust_height_by"),
            "fixture must exercise the fallback, not the MainWindow path",
        )

    def test_content_min_height_sees_past_the_explicit_minimum(self):
        """The shared rule reports the container's real layout minimum."""
        win, central, _group = self._host()
        self.assertEqual(
            SizeGripMixin.content_min_height(win),
            max(
                win.minimumSizeHint().height(),
                central.minimumSizeHint().height(),
            ),
        )

    def test_fallback_clamps_an_oversized_shrink_to_that_floor(self):
        """A shrink larger than the content can absorb stops at the real
        minimum, not at the under-reported window hint."""
        win, central, _group = self._host()
        floor = SizeGripMixin.content_min_height(win)
        self.assertGreater(floor, win.minimumSizeHint().height())

        CollapsableGroup._fallback_window_resize(win, win.height(), -10_000)
        QtWidgets.QApplication.processEvents()

        self.assertGreaterEqual(
            win.height(),
            floor,
            "fallback resized below the content's real minimum — the fixed rows "
            "are packed into overlap",
        )
        self.assertGreaterEqual(win.height(), central.minimumSizeHint().height())


class TestCollapseExpandRoundTripWhenClamped(QtBaseTestCase):
    """A collapse that the window minimum clamps short must not be undone
    by an unclamped expand — otherwise every cycle drifts the window taller
    (live: substance_workflow gained 43px per collapse/expand cycle)."""

    def test_expand_restores_only_what_collapse_removed(self):
        win = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        group = CollapsableGroup("grp")
        group.restore_state = False
        g_lay = QtWidgets.QVBoxLayout(group)
        for _ in range(4):
            row = QtWidgets.QLabel("row")
            row.setFixedHeight(19)
            g_lay.addWidget(row)
        lay.addWidget(group)

        # A tall growable sibling: it holds the window minimum up, so the
        # collapse cannot shrink by the group's full delta.
        keeper = QtWidgets.QTextEdit()
        keeper.setMinimumHeight(150)
        lay.addWidget(keeper)

        win.setCentralWidget(central)
        win.show()
        for _ in range(4):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

        start = win.height()
        group.setChecked(False)
        for _ in range(4):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        collapsed = win.height()
        self.assertLess(collapsed, start, "precondition: collapse shrinks some")

        group.setChecked(True)
        for _ in range(4):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        self.assertLessEqual(
            abs(win.height() - start),
            4,
            f"expand must land back at {start}, not {win.height()} — a "
            "min-clamped collapse paired with an unclamped expand drifts",
        )

    def test_expand_consumes_a_recorded_zero_shrink(self):
        """A collapse the window blocked ENTIRELY records a shrink of 0, and
        expand must then add nothing back. Guards the truthiness trap: `if
        self._collapse_shrink` reads a recorded 0 as "nothing recorded" and
        falls back to the group's own delta, reintroducing the drift."""
        win = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        group = CollapsableGroup("grp")
        group.restore_state = False
        g_lay = QtWidgets.QVBoxLayout(group)
        for _ in range(3):
            row = QtWidgets.QLabel("row")
            row.setFixedHeight(19)
            g_lay.addWidget(row)
        lay.addWidget(group)
        win.setCentralWidget(central)
        win.show()
        for _ in range(4):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

        # Collapse for real first, so expanding has a non-zero group delta —
        # otherwise the group delta is 0 and the assertion cannot tell the
        # fixed path from the buggy one.
        group.toggle_expand(False)
        for _ in range(4):
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

        deltas = []
        win.adjust_height_by = lambda d, baseline=None: deltas.append(d)
        group._collapse_shrink = 0  # ...but the window could not actually move

        group.toggle_expand(True)
        self.assertEqual(
            [d for d in deltas if d != 0],
            [],
            "expand grew a window whose collapse never shrank it",
        )


if __name__ == "__main__":
    unittest.main()
