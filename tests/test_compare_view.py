# !/usr/bin/python
# coding=utf-8
"""Tests for uitk.widgets.compare_view: two images wiped, side by side, blinked, or one alone."""

import unittest

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase, QtWait, setup_qt_application
from uitk.widgets.compare_view import CompareView

app = setup_qt_application()

RED, BLUE = (220, 30, 30), (30, 30, 220)


def _image(color):
    return np.full((40, 80, 3), color, np.uint8)


def _key(widget, kind, key=QtCore.Qt.Key_Space):
    QtWidgets.QApplication.sendEvent(widget, QtGui.QKeyEvent(kind, key, QtCore.Qt.NoModifier))


class TestCompareView(QtBaseTestCase):
    def compare(self, mode="split"):
        view = self.track_widget(CompareView(mode=mode))
        view.resize(320, 160)
        view.show()
        QtWait.pump()
        view.set_images(_image(RED), _image(BLUE))
        view.set_labels("Mix r6", "Reference")
        QtWait.pump()
        return view

    def color_at(self, image_view, x, y):
        """What the screen shows at image pixel (x, y) of *image_view*."""
        point = image_view.mapFromScene(QtCore.QPointF(x, y))
        return QtGui.QColor(image_view.grab().toImage().pixel(point)).getRgb()[:3]

    def test_split_shows_b_past_the_line_and_a_before_it(self):
        view = self.compare("split")
        self.assertEqual(self.color_at(view.view_a, 15, 20), RED)
        self.assertEqual(self.color_at(view.view_a, 65, 20), BLUE)
        self.assertFalse(view.view_b.isVisible())
        self.assertEqual((view._caption_a.text(), view._caption_b.text()), ("Mix r6", "Reference"))
        view.set_split_position(0.9)
        self.assertEqual(self.color_at(view.view_a, 65, 20), RED)
        self.assertAlmostEqual(view.split_position(), 0.9)

    def test_side_by_side_zooms_both_together(self):
        view = self.compare("side")
        self.assertTrue(view.view_b.isVisible())
        self.assertEqual(self.color_at(view.view_b, 40, 20), BLUE)
        target = view.view_a.viewport()
        local = QtCore.QPointF(view.view_a.mapFromScene(QtCore.QPointF(40, 20)))
        QtWidgets.QApplication.sendEvent(
            target,
            QtGui.QWheelEvent(
                local,
                QtCore.QPointF(target.mapToGlobal(local.toPoint())),
                QtCore.QPoint(),
                QtCore.QPoint(0, 240),
                QtCore.Qt.NoButton,
                QtCore.Qt.NoModifier,
                QtCore.Qt.NoScrollPhase,
                False,
            ),
        )
        self.assertAlmostEqual(view.view_b.zoom(), view.view_a.zoom(), places=4)

    def test_blink_shows_b_while_space_is_held(self):
        view = self.compare("blink")
        self.assertEqual(self.color_at(view.view_a, 40, 20), RED)
        _key(view, QtCore.QEvent.KeyPress)
        self.assertEqual(self.color_at(view.view_a, 40, 20), BLUE)
        self.assertEqual(view._caption_a.text(), "Reference")
        _key(view, QtCore.QEvent.KeyRelease)
        self.assertEqual(self.color_at(view.view_a, 40, 20), RED)
        _key(view, QtCore.QEvent.KeyPress)
        view.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.FocusOut))  # a release it never sees
        self.assertEqual(self.color_at(view.view_a, 40, 20), RED)

    def test_one_image_alone_and_the_mode_says_so(self):
        view = self.compare("split")
        modes = []
        view.mode_changed.connect(modes.append)
        view.set_mode("b")
        self.assertEqual(self.color_at(view.view_a, 15, 20), BLUE)
        view.set_mode("a")
        self.assertEqual(self.color_at(view.view_a, 65, 20), RED)
        view.set_mode("a")  # no change, no signal
        self.assertEqual(modes, ["b", "a"])
        with self.assertRaises(ValueError):
            view.set_mode("diff")

    def test_overlays_and_hover_come_from_the_inner_views(self):
        view = self.compare("side")
        clicked, hovered = [], []
        view.overlay_clicked.connect(clicked.append)
        view.hovered.connect(lambda x, y: hovered.append((x, y)))
        view.set_overlays([{"key": "wall", "points": [(0, 0), (40, 0), (40, 40), (0, 40)], "color": "#ffffff"}])
        self.assertEqual([o["key"] for o in view.view_b.overlays()], ["wall"])
        view.view_b.overlay_clicked.emit("wall")
        view.view_a.hovered.emit(3, 4)
        self.assertEqual((clicked, hovered), (["wall"], [(3, 4)]))


if __name__ == "__main__":
    unittest.main()
