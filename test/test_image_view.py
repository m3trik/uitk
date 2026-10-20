# !/usr/bin/python
# coding=utf-8
"""Tests for uitk.widgets.image_view: an image to inspect -- zoom, pan, overlays, a wipe."""

import unittest

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from conftest import QtBaseTestCase, QtWait, setup_qt_application
from uitk.widgets.image_view import ImageView

app = setup_qt_application()

RED, BLUE = (220, 30, 30), (30, 30, 220)


def _image(color, size=(80, 40)):
    width, height = size
    return np.full((height, width, 3), color, np.uint8)


def _mouse(view, kind, pos, button=QtCore.Qt.NoButton, buttons=None):
    """A mouse event on the view's viewport, where a QGraphicsView takes them."""
    target = view.viewport()
    local = QtCore.QPointF(pos)
    event = QtGui.QMouseEvent(
        kind,
        local,
        QtCore.QPointF(target.mapToGlobal(local.toPoint())),
        button,
        button if buttons is None else buttons,
        QtCore.Qt.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(target, event)


def _wheel(view, pos, notches=1):
    target = view.viewport()
    local = QtCore.QPointF(pos)
    event = QtGui.QWheelEvent(
        local,
        QtCore.QPointF(target.mapToGlobal(local.toPoint())),
        QtCore.QPoint(),
        QtCore.QPoint(0, 120 * notches),
        QtCore.Qt.NoButton,
        QtCore.Qt.NoModifier,
        QtCore.Qt.NoScrollPhase,
        False,
    )
    QtWidgets.QApplication.sendEvent(target, event)


class TestImageView(QtBaseTestCase):
    def view(self, image=None, size=(160, 80)):
        view = self.track_widget(ImageView())
        view.resize(*size)
        view.show()
        QtWait.pump()
        view.set_image(_image(RED) if image is None else image)
        QtWait.pump()
        return view

    def at(self, view, x, y):
        """The viewport point showing image pixel (x, y)."""
        return QtCore.QPointF(view.mapFromScene(QtCore.QPointF(x, y)))

    def test_an_array_shows_at_its_size_and_fills_the_view(self):
        view = self.view()
        self.assertEqual(view.image_size(), (80, 40))
        self.assertTrue(view.fitting())
        self.assertAlmostEqual(view.zoom(), 2.0, delta=0.15)
        shot = view.grab().toImage()
        self.assertEqual(QtGui.QColor(shot.pixel(80, 40)).getRgb()[:3], RED)

    def test_a_float_image_and_a_grey_one_show_too(self):
        view = self.view(np.full((10, 20, 3), 0.5, np.float32))
        self.assertEqual(view.image_size(), (20, 10))
        view.set_image(np.zeros((6, 8), np.uint8))
        self.assertEqual(view.image_size(), (8, 6))
        with self.assertRaises(ValueError):
            view.set_image(np.zeros((4, 4, 2), np.uint8))

    def test_a_16_bit_image_scales_by_its_range_not_clipped_white(self):
        half = np.full((4, 4, 3), 32768, np.uint16)
        shot = ImageView.to_pixmap(half).toImage()
        self.assertEqual(QtGui.QColor(shot.pixel(1, 1)).red(), 128)

    def test_the_wheel_zooms_about_the_cursor_and_frees_the_framing(self):
        view = self.view()
        changed = []
        view.view_changed.connect(lambda: changed.append(True))
        before = view.zoom()
        cursor = self.at(view, 20, 10)
        under = view.mapToScene(cursor.toPoint())
        _wheel(view, cursor)
        self.assertAlmostEqual(view.zoom(), before * ImageView.ZOOM_STEP, places=3)
        self.assertFalse(view.fitting())
        self.assertEqual(changed, [True])
        after = view.mapToScene(cursor.toPoint())
        self.assertAlmostEqual(after.x(), under.x(), delta=1.0)  # the point stays put
        self.assertAlmostEqual(after.y(), under.y(), delta=1.0)
        _mouse(view, QtCore.QEvent.MouseButtonDblClick, cursor, QtCore.Qt.LeftButton)
        self.assertTrue(view.fitting())

    def test_a_middle_drag_pans(self):
        view = self.view()
        _wheel(view, self.at(view, 40, 20), notches=3)  # room to pan
        start = view.view_state()["center"]
        point = self.at(view, 40, 20)
        _mouse(view, QtCore.QEvent.MouseButtonPress, point, QtCore.Qt.MiddleButton)
        _mouse(
            view,
            QtCore.QEvent.MouseMove,
            point + QtCore.QPointF(30, 0),
            QtCore.Qt.NoButton,
            QtCore.Qt.MiddleButton,
        )
        _mouse(view, QtCore.QEvent.MouseButtonRelease, point + QtCore.QPointF(30, 0), QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
        moved = view.view_state()["center"]
        self.assertAlmostEqual(moved[0] - start[0], -30 / view.zoom(), delta=1.0)

    def test_clicking_an_overlay_names_it_and_the_image_names_none(self):
        view = self.view()
        view.set_overlays(
            [
                {"key": "puck", "points": [(10, 10), (30, 10), (30, 30), (10, 30)], "closed": True, "color": "#ffcc00", "label": "puck"},
                {"key": "rim", "points": [(50, 5), (70, 35)], "closed": False, "color": "#00ccff"},
            ]
        )
        clicked = []
        view.overlay_clicked.connect(clicked.append)
        for x, y in ((20, 20), (60, 20), (75, 5)):  # inside, on the line, on neither
            point = self.at(view, x, y)
            _mouse(view, QtCore.QEvent.MouseButtonPress, point, QtCore.Qt.LeftButton)
            _mouse(view, QtCore.QEvent.MouseButtonRelease, point, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.assertEqual(clicked, ["puck", "rim", None])
        self.assertEqual([o["key"] for o in view.overlays()], ["puck", "rim"])

    def test_hovering_reports_the_image_pixel_and_leaving_it_says_so(self):
        view = self.view()
        seen = []
        view.hovered.connect(lambda x, y: seen.append((x, y)))
        _mouse(view, QtCore.QEvent.MouseMove, self.at(view, 12.5, 7.5))
        _mouse(view, QtCore.QEvent.MouseMove, QtCore.QPointF(-5, -5))
        self.assertEqual(seen, [(12, 7), (-1, -1)])

    def test_a_wipe_shows_the_second_image_past_its_line_and_drags(self):
        view = self.view()
        view.set_wipe(_image(BLUE), 0.5)
        QtWait.pump()
        shot = view.grab().toImage()
        left = self.at(view, 20, 20).toPoint()
        right = self.at(view, 60, 20).toPoint()
        self.assertEqual(QtGui.QColor(shot.pixel(left)).getRgb()[:3], RED)
        self.assertEqual(QtGui.QColor(shot.pixel(right)).getRgb()[:3], BLUE)
        moved = []
        view.wipe_moved.connect(moved.append)
        line = self.at(view, 40, 20)
        _mouse(view, QtCore.QEvent.MouseButtonPress, line, QtCore.Qt.LeftButton)
        _mouse(view, QtCore.QEvent.MouseMove, self.at(view, 60, 20), QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        _mouse(view, QtCore.QEvent.MouseButtonRelease, self.at(view, 60, 20), QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.assertAlmostEqual(view.wipe_position(), 0.75, delta=0.03)
        self.assertTrue(moved)
        view.set_wipe(None)
        self.assertIsNone(view.wipe_position())

    def test_a_view_state_frames_another_view_without_a_signal(self):
        a, b = self.view(), self.view()
        _wheel(a, self.at(a, 30, 15), notches=2)
        changed = []
        b.view_changed.connect(lambda: changed.append(True))
        b.set_view_state(a.view_state())
        self.assertAlmostEqual(b.zoom(), a.zoom(), places=4)
        self.assertEqual(changed, [])
        self.assertFalse(b.fitting())


class TestDrawTools(QtBaseTestCase):
    """A draw tool turns the left button into drawing; the shape arrives in image pixels."""

    def view(self):
        view = self.track_widget(ImageView())
        view.resize(160, 80)
        view.show()
        QtWait.pump()
        view.set_image(_image(RED))
        QtWait.pump()
        drawn = []
        view.shape_drawn.connect(lambda name, points: drawn.append((name, points)))
        return view, drawn

    def at(self, view, x, y):
        return QtCore.QPointF(view.mapFromScene(QtCore.QPointF(x, y)))

    def drag(self, view, start, end):
        _mouse(view, QtCore.QEvent.MouseButtonPress, self.at(view, *start), QtCore.Qt.LeftButton)
        _mouse(view, QtCore.QEvent.MouseMove, self.at(view, *end), QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        _mouse(view, QtCore.QEvent.MouseButtonRelease, self.at(view, *end), QtCore.Qt.LeftButton, QtCore.Qt.NoButton)

    def key(self, view, key):
        QtWidgets.QApplication.sendEvent(view, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier))

    def test_a_dragged_rectangle_arrives_as_its_corners_and_the_tool_is_done(self):
        view, drawn = self.view()
        clicked = []
        view.overlay_clicked.connect(clicked.append)
        view.set_tool("rect")
        self.assertEqual(view.tool(), "rect")
        self.drag(view, (10, 5), (50, 30))
        (name, points), = drawn
        self.assertEqual(name, "rect")
        np.testing.assert_allclose(points, [[10, 5], [50, 30]], atol=0.6)
        self.assertIsNone(view.tool())
        self.assertEqual(clicked, [])  # drawing is not clicking
        self.drag(view, (10, 5), (50, 30))  # the tool is spent: no second shape
        self.assertEqual(len(drawn), 1)

    def test_a_polygon_is_clicked_corner_by_corner_and_closed_by_a_double_click(self):
        view, drawn = self.view()
        view.set_tool("polygon")
        for x, y in ((10, 10), (60, 10), (60, 35)):
            _mouse(view, QtCore.QEvent.MouseButtonPress, self.at(view, x, y), QtCore.Qt.LeftButton)
            _mouse(view, QtCore.QEvent.MouseButtonRelease, self.at(view, x, y), QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        _mouse(view, QtCore.QEvent.MouseButtonDblClick, self.at(view, 60, 35), QtCore.Qt.LeftButton)
        (name, points), = drawn
        self.assertEqual(name, "polygon")
        np.testing.assert_allclose(points, [[10, 10], [60, 10], [60, 35]], atol=0.6)

    def test_enter_closes_a_polygon_and_esc_drops_a_tool(self):
        view, drawn = self.view()
        view.set_tool("polygon")
        for x, y in ((10, 10), (60, 10)):
            _mouse(view, QtCore.QEvent.MouseButtonPress, self.at(view, x, y), QtCore.Qt.LeftButton)
        self.key(view, QtCore.Qt.Key_Return)  # two corners: not yet a polygon
        self.assertEqual(drawn, [])
        _mouse(view, QtCore.QEvent.MouseButtonPress, self.at(view, 30, 35), QtCore.Qt.LeftButton)
        self.key(view, QtCore.Qt.Key_Return)
        self.assertEqual(len(drawn[0][1]), 3)
        view.set_tool("rect")
        self.key(view, QtCore.Qt.Key_Escape)
        self.assertIsNone(view.tool())
        self.drag(view, (10, 5), (50, 30))
        self.assertEqual(len(drawn), 1)  # dropped: nothing drawn

    def test_a_line_and_panning_while_a_tool_waits(self):
        view, drawn = self.view()
        view.set_tool("line")
        before = view.view_state()["center"]
        point = self.at(view, 40, 20)
        _mouse(view, QtCore.QEvent.MouseButtonPress, point, QtCore.Qt.MiddleButton)
        _mouse(view, QtCore.QEvent.MouseMove, point + QtCore.QPointF(20, 0), QtCore.Qt.NoButton, QtCore.Qt.MiddleButton)
        _mouse(view, QtCore.QEvent.MouseButtonRelease, point + QtCore.QPointF(20, 0), QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
        self.assertNotEqual(view.view_state()["center"], before)  # the middle button still pans
        self.assertEqual(view.tool(), "line")
        self.drag(view, (5, 20), (70, 20))
        self.assertEqual(drawn[0][0], "line")
        with self.assertRaises(KeyError):
            view.set_tool("lasso")

    def test_a_registered_tool_draws_like_the_built_ins(self):
        from uitk.widgets.image_view import ImageTool

        class _Point(ImageTool):
            def press(self, point):
                self.points = [point]
                return True

        ImageView.register_tool("point", _Point)
        self.addCleanup(lambda: ImageView.TOOLS.pop("point", None))
        view, drawn = self.view()
        view.set_tool("point")
        _mouse(view, QtCore.QEvent.MouseButtonPress, self.at(view, 30, 15), QtCore.Qt.LeftButton)
        np.testing.assert_allclose(drawn[0][1], [[30, 15]], atol=0.6)


if __name__ == "__main__":
    unittest.main()
