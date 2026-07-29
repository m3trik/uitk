# !/usr/bin/python
# coding=utf-8
"""Unit tests for the size-grip content-max lock.

A window whose visible content is entirely fixed in a direction cannot use
extra space in that direction — resizing it there only creates dead space
(reported as a "phantom extra header/footer" band in the scene exporter when
its output group is collapsed). ``SizeGripMixin.sync_window_max_to_content``
computes the content's real maximum from the layout and syncs the window's
maximum size to it; ``CornerSizeGrip`` applies the sync on mouse-press so a
grip drag can never create dead space, and clears it the same way once the
content becomes growable again (the sync is bidirectional, not a one-way
clamp).

Run standalone: python -m test.test_size_grip
"""

import unittest
from unittest.mock import patch

from conftest import QtBaseTestCase, setup_qt_application

app = setup_qt_application()

from qtpy import QtWidgets, QtCore, QtGui

from uitk.widgets.mixins.size_grip import (
    CornerSizeGrip,
    SizeGripMixin,
    QWIDGETSIZE_MAX,
)
from uitk.widgets.footer import Footer


def _flush():
    for _ in range(3):
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)


def _fixed_label(h):
    w = QtWidgets.QLabel("x")
    w.setMinimumSize(QtCore.QSize(0, h))
    w.setMaximumSize(QtCore.QSize(16777215, h))
    return w


def _build_window(growable):
    """Top-level widget with a footer + size grip; content fixed or growable."""
    win = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(win)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(0)
    if growable:
        lay.addWidget(QtWidgets.QTextEdit())
    else:
        lay.addWidget(_fixed_label(100))
    footer = Footer(add_size_grip=True)
    lay.addWidget(footer)
    return win, footer


def _press(grip):
    """Run CornerSizeGrip's press override with Qt's base press stubbed out.

    QSizeGrip's real ``mousePressEvent`` starts a (system) resize that
    wedges the offscreen platform's event loop, so it can't be entered in
    this harness. The override's own behavior (the content-max sync) plus
    its chaining to the base implementation is what we verify.
    """
    pos = QtCore.QPointF(2, 2)
    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress,
        pos,
        grip.mapToGlobal(pos.toPoint()),
        QtCore.Qt.LeftButton,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    with patch.object(QtWidgets.QSizeGrip, "mousePressEvent") as base_press:
        grip.mousePressEvent(event)
    base_press.assert_called_once()


class TestSyncWindowMaxToContent(QtBaseTestCase):
    """The pure sync: lock fixed directions, free growable ones."""

    def test_fully_fixed_content_locks_height_frees_width(self):
        win, _footer = _build_window(growable=False)
        self.track_widget(win)
        win.show()
        _flush()
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertLess(win.maximumHeight(), QWIDGETSIZE_MAX)
        # Children are width-expanding — width must remain free.
        self.assertEqual(win.maximumWidth(), QWIDGETSIZE_MAX)

    def test_growable_content_keeps_height_free(self):
        win, _footer = _build_window(growable=True)
        self.track_widget(win)
        win.show()
        _flush()
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertEqual(win.maximumHeight(), QWIDGETSIZE_MAX)

    def test_sync_trims_existing_dead_space(self):
        win, _footer = _build_window(growable=False)
        self.track_widget(win)
        win.show()
        _flush()
        tight = win.sizeHint().height()
        win.resize(win.width(), tight + 150)  # dead space: nothing can use it
        _flush()
        SizeGripMixin.sync_window_max_to_content(win)
        _flush()
        self.assertLessEqual(
            win.height(),
            tight + 4,
            "sync must snap off dead space when content is fully fixed",
        )

    def test_sync_clears_stale_lock_when_content_becomes_growable(self):
        win, _footer = _build_window(growable=True)
        self.track_widget(win)
        win.show()
        _flush()
        win.setMaximumHeight(200)  # stale lock from an earlier fixed state
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertEqual(win.maximumHeight(), QWIDGETSIZE_MAX)

    def test_layoutless_window_is_untouched(self):
        win = self.track_widget(QtWidgets.QWidget())
        win.show()
        _flush()
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertEqual(win.maximumHeight(), QWIDGETSIZE_MAX)
        self.assertEqual(win.maximumWidth(), QWIDGETSIZE_MAX)


class TestContentMaxSpacersAndContainers(QtBaseTestCase):
    """The collapsed scene-exporter profile: fixed rows inside a
    default-policy QGroupBox with NO surplus absorber. Qt's
    ``QLayout.maximumSize()`` calls the group box unbounded — but it is not
    content that can use extra space, so the cap must see through it. A
    grow-policy spacer, on the other hand, IS the layout's designated
    absorber (the mayatk/tentacle panel profile is fixed rows + a trailing
    Expanding spacer): its direction must stay free, or the grip locks on
    essentially every panel window. A genuinely growable leaf (scroll area /
    Expanding policy) must also unlock.
    """

    @staticmethod
    def _panel_window(growable_row=False, spacer_policy=None):
        win = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(win)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        lay.addWidget(_fixed_label(19))  # header
        group = QtWidgets.QGroupBox("grp")  # default Preferred policy, no max
        g_lay = QtWidgets.QVBoxLayout(group)
        g_lay.setContentsMargins(0, 0, 0, 0)
        for _ in range(3):
            g_lay.addWidget(_fixed_label(19))  # fixed rows
        if growable_row:
            g_lay.addWidget(QtWidgets.QTextEdit())
        lay.addWidget(group)
        if spacer_policy is not None:
            lay.addSpacerItem(
                QtWidgets.QSpacerItem(
                    0, 10, QtWidgets.QSizePolicy.Minimum, spacer_policy
                )
            )
        lay.addWidget(_fixed_label(19))  # footer
        return win

    def test_container_without_absorber_keeps_cap_finite(self):
        win = self.track_widget(self._panel_window())
        win.show()
        _flush()
        max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertLess(
            max_h, QWIDGETSIZE_MAX,
            "a default-policy group box is not content — all real rows are "
            "fixed and nothing absorbs surplus, so the height cap is finite",
        )
        self.assertEqual(max_w, QWIDGETSIZE_MAX, "width stays free")

    def test_fixed_spacer_keeps_cap_finite(self):
        win = self.track_widget(
            self._panel_window(spacer_policy=QtWidgets.QSizePolicy.Fixed)
        )
        win.show()
        _flush()
        _max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertLess(max_h, QWIDGETSIZE_MAX, "a Fixed spacer is a mere gap")

    def test_expanding_spacer_frees_the_direction(self):
        """Regression: fixed rows + trailing Expanding spacer is the standard
        panel .ui profile — treating the spacer as non-content locked vertical
        grip resize on nearly every window in the ecosystem."""
        win = self.track_widget(
            self._panel_window(spacer_policy=QtWidgets.QSizePolicy.Expanding)
        )
        win.show()
        _flush()
        _max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertEqual(
            max_h, QWIDGETSIZE_MAX,
            "an Expanding spacer is the designer's surplus absorber — the "
            "direction must stay resizable",
        )

    def test_sync_respects_an_explicit_fixed_size_lock(self):
        """A window stamped FIXED_LOCK_PROP (the fit_to_window rigid-lock
        contract — native-menu wrappers) must NOT be freed by the content
        sync, whatever the content hints say."""
        win = self.track_widget(
            self._panel_window(spacer_policy=QtWidgets.QSizePolicy.Expanding)
        )
        win.show()
        _flush()
        win.setFixedSize(222, 333)
        win.setProperty(SizeGripMixin.FIXED_LOCK_PROP, True)
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertEqual(
            (win.maximumWidth(), win.maximumHeight()),
            (222, 333),
            "sync_window_max_to_content undid an explicit size lock",
        )

    def test_sync_pinned_lock_still_heals(self):
        """A lock the sync ITSELF produced (fully-fixed content pins max down
        to min in both axes) is not a deliberate contract — when the content
        later becomes growable, the next sync must free it again. This is why
        the fixed-lock guard is an explicit property, not a min==max
        inference."""
        win = self.track_widget(QtWidgets.QWidget())
        lay = QtWidgets.QVBoxLayout(win)
        fixed = QtWidgets.QPushButton("rigid")
        fixed.setFixedSize(120, 24)
        lay.addWidget(fixed)
        win.show()
        _flush()
        win.setMinimumSize(win.sizeHint())
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertEqual(
            win.minimumSize(), win.maximumSize(),
            "precondition: fully-fixed content should pin max down to min",
        )
        grower = QtWidgets.QTextEdit()  # Expanding both axes
        lay.addWidget(grower)
        _flush()
        SizeGripMixin.sync_window_max_to_content(win)
        # Width stays capped by the fixed button (the walk's min-across
        # perpendicular rule); the heal shows on the box axis.
        self.assertEqual(
            win.maximumHeight(),
            QWIDGETSIZE_MAX,
            "sync-pinned lock failed to heal once the content could grow",
        )

    def test_spacing_matches_qt_for_empty_neighbours(self):
        """Qt adds a box-layout gap before an item ONLY when the preceding
        item is non-empty — hidden widgets and QSpacerItems are "empty", so
        the spacing next to them is suppressed. A flat ``(visible-1) *
        spacing`` therefore over-reports the cap by one gap per
        empty-preceded item, and that surplus is dead space the window can
        be stretched into (live: mesh_convert's collapse cycle drifted 6px
        taller each expand because the cap sat one spacing above the
        content's real height)."""
        win = self.track_widget(QtWidgets.QWidget())
        lay = QtWidgets.QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        hidden = _fixed_label(19)
        lay.addWidget(hidden)
        lay.addWidget(_fixed_label(53))
        lay.addSpacerItem(
            QtWidgets.QSpacerItem(
                0, 10, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
            )
        )
        lay.addWidget(_fixed_label(19))
        hidden.hide()
        win.show()
        _flush()
        _max_w, max_h = SizeGripMixin.content_max_size(win)
        # Every item is fixed, so the cap must be EXACTLY what Qt lays out —
        # anything more is dead space the content cannot use.
        self.assertEqual(
            max_h,
            win.sizeHint().height(),
            "content cap must match Qt's own laid-out height; surplus here is "
            "mis-counted spacing next to the hidden widget / spacer",
        )

    def test_growable_leaf_inside_container_unlocks(self):
        win = self.track_widget(self._panel_window(growable_row=True))
        win.show()
        _flush()
        _max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertEqual(max_h, QWIDGETSIZE_MAX)

    def test_chrome_is_not_inferred_from_transient_geometry(self):
        """QMainWindow chrome (toolbars etc.) must come from size HINTS, not
        from ``window.height() - central.height()``: mid-restore the window
        is already at its restored height while the central widget's
        geometry lags one layout pass behind, and that transient lag read as
        permanent chrome — inflating the cap by exactly the lag (live: a
        geometry-restored uv panel kept a 19px dead band because the cap
        followed the stale oversize instead of exposing it)."""
        win = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        for _ in range(3):
            lay.addWidget(_fixed_label(19))
        win.setCentralWidget(central)
        win.show()
        _flush()
        _w, cap0 = SizeGripMixin.content_max_size(win)
        self.assertLess(cap0, QWIDGETSIZE_MAX, "precondition: finite cap")
        # Restored-geometry ordering: the window is resized while not
        # exposed (restoreGeometry runs before the first paint), so the
        # central widget's geometry lags until the next layout pass.
        win.hide()
        win.resize(win.width(), win.height() + 19)
        _w, cap1 = SizeGripMixin.content_max_size(win)
        self.assertEqual(
            cap1, cap0,
            "a transient window/central height mismatch is not chrome",
        )

    def test_chrome_reads_fresh_hints_after_bar_visibility_change(self):
        """QMainWindowLayout CACHES its minimum size: hiding a bar (or the
        header, mid-show) leaves the window hint stale-high until the next
        layout pass, and the stale delta read as permanent chrome — the
        restored uv panel capped at its stale oversize because of it. The
        chrome measurement must invalidate the window layout first."""
        win = self.track_widget(QtWidgets.QMainWindow())
        central = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(central)
        for _ in range(3):
            lay.addWidget(_fixed_label(19))
        win.setCentralWidget(central)
        toolbar = win.addToolBar("bar")
        toolbar.addWidget(_fixed_label(19))
        win.show()
        _flush()
        _w, cap_with_bar = SizeGripMixin.content_max_size(win)
        self.assertLess(cap_with_bar, QWIDGETSIZE_MAX, "precondition")
        toolbar.hide()  # deliberately NOT flushed — cache is stale
        _w, cap_without_bar = SizeGripMixin.content_max_size(win)
        self.assertLess(
            cap_without_bar, cap_with_bar,
            "hiding real chrome must drop the cap immediately — a stale "
            "window-layout cache must not keep counting it",
        )

    def test_bare_preferred_label_keeps_cap_unbounded(self):
        """A grow-policy leaf without an explicit max (bare QLabel) CAN take
        extra space per Qt semantics — the cap must not over-lock it."""
        win = self.track_widget(QtWidgets.QWidget())
        lay = QtWidgets.QVBoxLayout(win)
        lay.addWidget(QtWidgets.QLabel("free"))  # Preferred vertical policy
        win.show()
        _flush()
        _max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertEqual(max_h, QWIDGETSIZE_MAX)


class TestGripAutoVisibility(QtBaseTestCase):
    """The grip auto-hides on a window that cannot resize in EITHER
    direction (min == max both ways — e.g. a fit_to_window rigid lock) and
    re-shows the moment a direction frees. Single-axis locks keep the grip:
    the hover cursor already signals the remaining axis."""

    def test_grip_hides_on_rigidly_locked_window(self):
        win, footer = _build_window(growable=True)
        self.track_widget(win)
        win.show()
        _flush()
        self.assertFalse(footer.size_grip.isHidden(), "precondition: visible")
        win.setFixedSize(222, 333)
        win.setProperty(SizeGripMixin.FIXED_LOCK_PROP, True)
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertTrue(
            footer.size_grip.isHidden(),
            "grip is a dead affordance on a window locked in both directions",
        )

    def test_grip_reshows_when_lock_clears(self):
        win, footer = _build_window(growable=True)
        self.track_widget(win)
        win.show()
        _flush()
        win.setFixedSize(222, 333)
        win.setProperty(SizeGripMixin.FIXED_LOCK_PROP, True)
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertTrue(footer.size_grip.isHidden(), "precondition: hidden")
        win.setProperty(SizeGripMixin.FIXED_LOCK_PROP, None)
        win.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertFalse(
            footer.size_grip.isHidden(),
            "grip must come back once the window is resizable again",
        )

    def test_single_axis_lock_keeps_grip_visible(self):
        """The standard panel profile: height locked, width free — the grip
        stays, with the cursor carrying the axis information."""
        win, footer = _build_window(growable=False)
        self.track_widget(win)
        win.show()
        _flush()
        win.setMinimumHeight(win.sizeHint().height())
        SizeGripMixin.sync_window_max_to_content(win)
        self.assertLess(win.maximumHeight(), QWIDGETSIZE_MAX, "precondition")
        self.assertFalse(footer.size_grip.isHidden())


class TestGripPressAppliesSync(QtBaseTestCase):
    """CornerSizeGrip must sync the window max on press."""

    def test_press_locks_fixed_window(self):
        win, footer = _build_window(growable=False)
        self.track_widget(win)
        win.show()
        _flush()
        grip = footer.size_grip
        self.assertIsInstance(grip, CornerSizeGrip)
        _press(grip)
        self.assertLess(win.maximumHeight(), QWIDGETSIZE_MAX)
        self.assertEqual(win.maximumWidth(), QWIDGETSIZE_MAX)

    def test_press_frees_growable_window(self):
        win, footer = _build_window(growable=True)
        self.track_widget(win)
        win.show()
        _flush()
        win.setMaximumHeight(200)  # stale lock
        _press(footer.size_grip)
        self.assertEqual(win.maximumHeight(), QWIDGETSIZE_MAX)


if __name__ == "__main__":
    unittest.main()
