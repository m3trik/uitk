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


class TestContentMaxSeesThroughSpacersAndContainers(QtBaseTestCase):
    """The tentacle-panel profile (e.g. the nurbs window): fixed rows inside a
    default-policy QGroupBox, plus a trailing Expanding spacer. Qt's
    ``QLayout.maximumSize()`` calls both unbounded — but neither is content
    that can use extra space, so the cap must see through them. A genuinely
    growable leaf (scroll area / Expanding policy) must still unlock.
    """

    @staticmethod
    def _nurbs_like_window(growable_row=False):
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
        lay.addSpacerItem(
            QtWidgets.QSpacerItem(
                0, 10,
                QtWidgets.QSizePolicy.Minimum,
                QtWidgets.QSizePolicy.Expanding,
            )
        )
        lay.addWidget(_fixed_label(19))  # footer
        return win

    def test_spacer_and_container_do_not_unbound_the_cap(self):
        win = self.track_widget(self._nurbs_like_window())
        win.show()
        _flush()
        max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertLess(
            max_h, QWIDGETSIZE_MAX,
            "an Expanding spacer / default-policy group box is not content — "
            "all real rows are fixed, so the height cap must be finite",
        )
        self.assertEqual(max_w, QWIDGETSIZE_MAX, "width stays free")

    def test_growable_leaf_inside_container_unlocks(self):
        win = self.track_widget(self._nurbs_like_window(growable_row=True))
        win.show()
        _flush()
        _max_w, max_h = SizeGripMixin.content_max_size(win)
        self.assertEqual(max_h, QWIDGETSIZE_MAX)

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
