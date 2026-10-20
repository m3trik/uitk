# !/usr/bin/python
# coding=utf-8
"""An image to look at closely: zoom about the cursor, pan, and shapes drawn over it."""

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Type

from qtpy import QtCore, QtGui, QtWidgets

from uitk.widgets.mixins.attributes import AttributesMixin


class _ImageViewInternal:
    """Conversions behind :class:`ImageView`."""

    @staticmethod
    def to_pixmap(image: Any) -> Optional[QtGui.QPixmap]:
        """*image* as a QPixmap: a QPixmap, a QImage, or an ``(h, w)`` /
        ``(h, w, 3|4)`` array -- uint8, another integer type (scaled by its
        range), or float in 0..1 (clipped).

        Raises:
            ValueError: an array of another shape.
        """
        if image is None:
            return None
        if isinstance(image, QtGui.QPixmap):
            return image
        if isinstance(image, QtGui.QImage):
            return QtGui.QPixmap.fromImage(image)
        import numpy as np  # only an array needs it

        arr = np.asarray(image)
        if np.issubdtype(arr.dtype, np.integer) and arr.dtype != np.uint8:
            arr = arr.astype(np.float32) / np.iinfo(arr.dtype).max
        if arr.dtype != np.uint8:
            arr = (np.clip(arr.astype(np.float32), 0.0, 1.0) * 255.0 + 0.5).astype(
                np.uint8
            )
        if arr.ndim == 2:
            arr = np.repeat(arr[..., None], 3, axis=2)
        if arr.ndim != 3 or arr.shape[2] not in (3, 4):
            raise ValueError(f"An image is (h, w, 3) or (h, w, 4); got {arr.shape}.")
        arr = np.ascontiguousarray(arr)
        height, width, channels = arr.shape
        fmt = (
            QtGui.QImage.Format_RGB888 if channels == 3 else QtGui.QImage.Format_RGBA8888
        )
        # copy(): the QImage would otherwise borrow the array's memory.
        qimage = QtGui.QImage(arr.data, width, height, channels * width, fmt).copy()
        return QtGui.QPixmap.fromImage(qimage)

    @staticmethod
    def path_of(points: Sequence[Sequence[float]], closed: bool) -> QtGui.QPainterPath:
        """A painter path through *points* (image pixels), closed or not."""
        path = QtGui.QPainterPath()
        if not points:
            return path
        path.moveTo(float(points[0][0]), float(points[0][1]))
        for x, y in points[1:]:
            path.lineTo(float(x), float(y))
        if closed:
            path.closeSubpath()
        return path


class ImageTool:
    """A way to draw a shape on an :class:`ImageView`, point by point in image pixels.

    While it is the view's tool, the view hands it the left button's presses,
    moves (with the button held, or -- for a click-by-click tool -- without)
    and releases, and Enter or a double-click as :meth:`finish`. A method
    answering True means the shape is drawn: the view emits
    ``shape_drawn(name, points)`` with :meth:`result` and drops the tool. A new
    tool is a subclass and one :meth:`ImageView.register_tool`.
    """

    #: Whether its preview closes back to the first point.
    closed = True
    #: Whether a move with no button held still moves the preview (a polygon's
    #: next corner follows the cursor).
    hovers = False

    def __init__(self):
        self.points: List[Tuple[float, float]] = []

    def press(self, point: Tuple[float, float]) -> bool:
        return False

    def move(self, point: Tuple[float, float]) -> None:
        pass

    def release(self, point: Tuple[float, float]) -> bool:
        return False

    def finish(self) -> bool:
        return False

    def preview(self) -> List[Tuple[float, float]]:
        """The points the dashed preview runs through."""
        return list(self.points)

    def result(self) -> List[Tuple[float, float]]:
        """What the drawn shape is, in image pixels."""
        return list(self.points)


class _DragTool(ImageTool):
    """Press, drag, release: two points (a box's corners, a line's ends)."""

    def press(self, point):
        self.points = [point, point]
        return False

    def move(self, point):
        if self.points:
            self.points[1] = point

    def release(self, point):
        if not self.points:
            return False
        self.points[1] = point
        (x0, y0), (x1, y1) = self.points
        return (x0, y0) != (x1, y1)


class _RectTool(_DragTool):
    def preview(self):
        if not self.points:
            return []
        (x0, y0), (x1, y1) = self.points
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


class _EllipseTool(_DragTool):
    """The box the ellipse fills: its two corners are the result."""

    def preview(self):
        if not self.points:
            return []
        (x0, y0), (x1, y1) = self.points
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
        steps = 48
        return [
            (cx + rx * math.cos(2 * math.pi * i / steps), cy + ry * math.sin(2 * math.pi * i / steps))
            for i in range(steps)
        ]


class _LineTool(_DragTool):
    closed = False


class _PolygonTool(ImageTool):
    """A click per corner (the next follows the cursor); Enter or a
    double-click closes it once it has three."""

    hovers = True

    def __init__(self):
        super().__init__()
        self._cursor: Optional[Tuple[float, float]] = None

    def press(self, point):
        if not self.points or self.points[-1] != point:
            self.points.append(point)
        return False

    def move(self, point):
        self._cursor = point

    def finish(self):
        return len(self.points) >= 3

    def preview(self):
        return list(self.points) + ([self._cursor] if self._cursor and self.points else [])


class ImageView(QtWidgets.QGraphicsView, AttributesMixin, _ImageViewInternal):
    """An image to inspect: the wheel zooms about the cursor, the middle button
    (or Space and the left button) pans, a double-click fits.

    Shapes drawn over the image are plain values in image pixels
    (:meth:`set_overlays`); clicking one names it. A second image can be wiped
    over the first (:meth:`set_wipe`), the split a compositor's viewer shows,
    its line dragged sideways. Two views lock together through
    :meth:`view_state` / :meth:`set_view_state` and :attr:`view_changed`.

    A draw tool (:meth:`set_tool`: ``rect``, ``ellipse``, ``polygon``,
    ``line``; :meth:`register_tool` adds one) turns the left button into
    drawing: the shape arrives as ``shape_drawn(name, points)`` in image pixels
    (a box's corners, a line's ends, a polygon's corners) and the tool is done;
    Esc drops it.

    Signals:
        overlay_clicked(object): The key of the overlay a click landed on;
            ``None`` for the image itself.
        hovered(int, int): The image pixel under the cursor; ``(-1, -1)``
            once it leaves the image.
        view_changed(): The user zoomed or panned (not :meth:`set_view_state`).
        wipe_moved(float): The wipe line dragged to this position (0..1).
        shape_drawn(str, list): A draw tool's shape: its name and points.
    """

    designer_spec = {"icon": "image", "object_name": "image_view", "size": (320, 200)}

    overlay_clicked = QtCore.Signal(object)
    hovered = QtCore.Signal(int, int)
    view_changed = QtCore.Signal()
    wipe_moved = QtCore.Signal(float)
    shape_drawn = QtCore.Signal(str, list)

    #: Draw tools by name (:meth:`register_tool` adds one).
    TOOLS: Dict[str, Type[ImageTool]] = {
        "rect": _RectTool,
        "ellipse": _EllipseTool,
        "polygon": _PolygonTool,
        "line": _LineTool,
    }

    #: Zoom factor per wheel notch, and the zoom's bounds.
    ZOOM_STEP = 1.25
    ZOOM_LIMITS = (0.02, 64.0)
    #: Screen pixels: how near an open shape a click picks it, and how near
    #: the wipe line a press takes it.
    HIT_TOLERANCE = 6
    WIPE_GRAB = 6
    #: Zoomed in this far, pixels show as squares (nearest) rather than smoothed.
    CRISP_ZOOM = 2.0

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._image = QtWidgets.QGraphicsPixmapItem()
        self._scene.addItem(self._image)
        # The wiped-over image: clipped to the right of the wipe line.
        self._wipe_clip = QtWidgets.QGraphicsRectItem()
        self._wipe_clip.setFlag(QtWidgets.QGraphicsItem.ItemClipsChildrenToShape, True)
        self._wipe_clip.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        self._wipe_image = QtWidgets.QGraphicsPixmapItem(self._wipe_clip)
        self._scene.addItem(self._wipe_clip)
        line_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.5)
        line_pen.setCosmetic(True)
        self._wipe_line = QtWidgets.QGraphicsLineItem()
        self._wipe_line.setPen(line_pen)
        self._wipe_line.setZValue(10)
        self._scene.addItem(self._wipe_line)
        self._wipe: Optional[float] = None
        self._overlays: List[Dict[str, Any]] = []
        self._overlay_items: List[QtWidgets.QGraphicsItem] = []
        self._fitting = True  # fit on resize until the user frames it
        self._pan_from: Optional[QtCore.QPointF] = None
        self._press: Optional[QtCore.QPointF] = None
        self._dragging_wipe = False
        self._space = False
        self._tool: Optional[ImageTool] = None
        self._tool_name: Optional[str] = None
        dashed = QtGui.QPen(QtGui.QColor(255, 255, 255, 230), 1.5, QtCore.Qt.DashLine)
        dashed.setCosmetic(True)
        # Made here and handed to the scene, as every item this widget keeps is:
        # one the scene makes (``addPath``) has a C++-owned wrapper, which a
        # Designer load (QUiLoader) invalidates once the panel is built.
        self._tool_preview = QtWidgets.QGraphicsPathItem()
        self._tool_preview.setPen(dashed)
        self._tool_preview.setZValue(30)
        self._scene.addItem(self._tool_preview)

        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.setBackgroundBrush(self.palette().color(QtGui.QPalette.Dark))
        self.set_attributes(**kwargs)

    # ------------------------------------------------------------------ the image
    def set_image(self, image: Any) -> None:
        """Show *image* (see :meth:`to_pixmap`; ``None`` clears). A view the
        user has framed keeps its framing; an unframed one fits the image."""
        pixmap = self.to_pixmap(image)
        self._image.setPixmap(pixmap or QtGui.QPixmap())
        self._update_scene_rect()
        self._place_wipe()
        if self._fitting:
            self.fit()

    def image_size(self) -> Tuple[int, int]:
        """``(width, height)`` of the image in pixels (``(0, 0)`` with none)."""
        pixmap = self._image.pixmap()
        return (pixmap.width(), pixmap.height())

    def _update_scene_rect(self) -> None:
        """Room to pan past the image's edges, by its own size each way."""
        width, height = self.image_size()
        self._scene.setSceneRect(-width, -height, 3 * width, 3 * height)

    # ------------------------------------------------------------------ framing
    def zoom(self) -> float:
        """Screen pixels per image pixel."""
        return self.transform().m11()

    def fit(self) -> None:
        """Frame the whole image (and keep it framed as the view resizes)."""
        width, height = self.image_size()
        if width and height and self.viewport().width() > 1:
            self.fitInView(QtCore.QRectF(0, 0, width, height), QtCore.Qt.KeepAspectRatio)
        self._fitting = True
        self._zoomed()

    def fitting(self) -> bool:
        """Whether the view keeps the whole image framed (until the user frames it)."""
        return self._fitting

    def actual_size(self) -> None:
        """One image pixel to one screen pixel, about the view's centre."""
        centre = self.mapToScene(self.viewport().rect().center())
        self.setTransform(QtGui.QTransform())
        self.centerOn(centre)
        self._fitting = False
        self._zoomed()

    def view_state(self) -> Dict[str, Any]:
        """``{"zoom", "center": [x, y]}`` (image pixels): what :meth:`set_view_state` takes."""
        centre = self.mapToScene(self.viewport().rect().center())
        return {"zoom": self.zoom(), "center": [centre.x(), centre.y()]}

    def set_view_state(self, state: Mapping[str, Any]) -> None:
        """Frame the view as *state* says (emits no :attr:`view_changed`)."""
        zoom = float(state.get("zoom", 1.0))
        self.setTransform(QtGui.QTransform.fromScale(zoom, zoom))
        x, y = state.get("center", (0.0, 0.0))
        self.centerOn(float(x), float(y))
        self._fitting = False
        self._zoomed()

    def _zoomed(self) -> None:
        """Crisp pixels when zoomed far in, smoothed otherwise."""
        mode = (
            QtCore.Qt.FastTransformation
            if self.zoom() >= self.CRISP_ZOOM
            else QtCore.Qt.SmoothTransformation
        )
        self._image.setTransformationMode(mode)
        self._wipe_image.setTransformationMode(mode)

    # ------------------------------------------------------------------ the wipe
    def set_wipe(self, image: Any, position: float = 0.5) -> None:
        """Show *image* over the first right of a vertical line at *position*
        (0..1 of the width); ``None`` removes the wipe."""
        pixmap = self.to_pixmap(image)
        self._wipe = None if pixmap is None else min(1.0, max(0.0, float(position)))
        self._wipe_image.setPixmap(pixmap or QtGui.QPixmap())
        self._place_wipe()

    def wipe_position(self) -> Optional[float]:
        """Where the wipe line is (0..1), or ``None`` with no wipe."""
        return self._wipe

    def set_wipe_position(self, position: float) -> None:
        if self._wipe is not None:
            self._wipe = min(1.0, max(0.0, float(position)))
            self._place_wipe()

    def _place_wipe(self) -> None:
        width, height = self.image_size()
        shown = self._wipe is not None and width > 0
        self._wipe_clip.setVisible(shown)
        self._wipe_line.setVisible(shown)
        if shown:
            x = self._wipe * width
            self._wipe_clip.setRect(x, 0, width - x, height)
            self._wipe_line.setLine(x, 0, x, height)

    def _near_wipe(self, view_pos: QtCore.QPointF) -> bool:
        if self._wipe is None:
            return False
        line_x = self.mapFromScene(QtCore.QPointF(self._wipe * self.image_size()[0], 0)).x()
        return abs(view_pos.x() - line_x) <= self.WIPE_GRAB

    # ------------------------------------------------------------------ overlays
    def set_overlays(self, overlays: Sequence[Mapping[str, Any]]) -> None:
        """Draw *overlays* over the image: each ``{"key", "points": [(x, y), ...]
        in image pixels, "closed", "color": "#rrggbb", "label" (optional),
        "selected" (optional)}``. Replaces what was drawn."""
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items = []
        self._overlays = [dict(o) for o in overlays]
        for overlay in self._overlays:
            color = QtGui.QColor(overlay.get("color") or "#ffffff")
            selected = bool(overlay.get("selected"))
            pen = QtGui.QPen(color, 3.0 if selected else 1.5)
            pen.setCosmetic(True)
            path = self.path_of(overlay.get("points") or (), bool(overlay.get("closed", True)))
            shape = QtWidgets.QGraphicsPathItem(path)
            shape.setPen(pen)
            shape.setZValue(20 if selected else 15)
            self._scene.addItem(shape)
            self._overlay_items.append(shape)
            label = overlay.get("label")
            if label and overlay.get("points"):
                text = QtWidgets.QGraphicsSimpleTextItem(str(label))
                text.setBrush(color)
                text.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
                x, y = overlay["points"][0]
                text.setPos(float(x), float(y))
                text.setZValue(21)
                self._scene.addItem(text)
                self._overlay_items.append(text)

    def overlays(self) -> List[Dict[str, Any]]:
        """What :meth:`set_overlays` was given."""
        return [dict(o) for o in self._overlays]

    def overlay_at(self, view_pos: QtCore.QPointF) -> Any:
        """The key of the topmost overlay at *view_pos* (viewport pixels), or ``None``.

        A closed shape is hit inside it; an open one (a line) within
        :attr:`HIT_TOLERANCE` screen pixels of it.
        """
        point = self.mapToScene(view_pos.toPoint())
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(2 * self.HIT_TOLERANCE / max(self.zoom(), 1e-6))
        for overlay in reversed(self._overlays):
            closed = bool(overlay.get("closed", True))
            path = self.path_of(overlay.get("points") or (), closed)
            if (closed and path.contains(point)) or stroker.createStroke(path).contains(
                point
            ):
                return overlay.get("key")
        return None

    # ------------------------------------------------------------------ draw tools
    @classmethod
    def register_tool(cls, name: str, tool: Type[ImageTool]) -> None:
        """Add (or replace) draw tool *name*."""
        cls.TOOLS = dict(cls.TOOLS, **{name: tool})

    def set_tool(self, name: Optional[str]) -> None:
        """Draw with tool *name* (one shape), or ``None`` to stop drawing.

        Raises:
            KeyError: no tool of that name.
        """
        if name is not None and name not in self.TOOLS:
            raise KeyError(f"No draw tool {name!r}; tools: {sorted(self.TOOLS)}.")
        self._tool = self.TOOLS[name]() if name is not None else None
        self._tool_name = name
        self._show_tool()
        self.viewport().setCursor(QtCore.Qt.CrossCursor if name else QtCore.Qt.ArrowCursor)
        if name:
            self.setFocus()  # Enter and Esc reach it

    def tool(self) -> Optional[str]:
        """The draw tool in use, or ``None``."""
        return self._tool_name

    def _scene_point(self, view_pos: QtCore.QPointF) -> Tuple[float, float]:
        point = self.mapToScene(view_pos.toPoint())
        return (round(point.x(), 3), round(point.y(), 3))

    def _show_tool(self) -> None:
        points = self._tool.preview() if self._tool is not None else []
        closed = self._tool.closed if self._tool is not None else False
        self._tool_preview.setPath(self.path_of(points, closed and len(points) > 2))

    def _tool_done(self) -> None:
        name, points = self._tool_name, [list(p) for p in self._tool.result()]
        self.set_tool(None)
        self.shape_drawn.emit(name, points)

    # ------------------------------------------------------------------ input
    def _image_pixel(self, view_pos: QtCore.QPointF) -> Tuple[int, int]:
        point = self.mapToScene(view_pos.toPoint())
        width, height = self.image_size()
        x, y = int(point.x() // 1), int(point.y() // 1)
        return (x, y) if 0 <= x < width and 0 <= y < height else (-1, -1)

    @staticmethod
    def _pos(event) -> QtCore.QPointF:
        return event.position() if hasattr(event, "position") else QtCore.QPointF(event.pos())

    def wheelEvent(self, event) -> None:
        notches = (event.angleDelta().y() or event.angleDelta().x()) / 120.0
        if not notches:
            return
        factor = self.ZOOM_STEP**notches
        low, high = self.ZOOM_LIMITS
        factor = min(max(self.zoom() * factor, low), high) / self.zoom()
        # About the wheel's own point: Qt's AnchorUnderMouse reads the last
        # mouse MOVE, and a wheel can come before any (a focus change, a tablet).
        point = self._pos(event).toPoint()
        under = self.mapToScene(point)
        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
        self.scale(factor, factor)
        drift = self.mapToScene(point) - under
        self.translate(drift.x(), drift.y())
        self.setTransformationAnchor(anchor)
        self._fitting = False
        self._zoomed()
        self.view_changed.emit()
        event.accept()

    def mousePressEvent(self, event) -> None:
        pos = self._pos(event)
        button = event.button()
        if button == QtCore.Qt.MiddleButton or (
            button == QtCore.Qt.LeftButton and self._space
        ):
            self._pan_from = pos
            self.viewport().setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return
        if button == QtCore.Qt.LeftButton and self._tool is not None:
            if self._tool.press(self._scene_point(pos)):
                self._tool_done()
            else:
                self._show_tool()
            event.accept()
            return
        if button == QtCore.Qt.LeftButton and self._near_wipe(pos):
            self._dragging_wipe = True
            event.accept()
            return
        if button == QtCore.Qt.LeftButton:
            self._press = pos
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = self._pos(event)
        if self._pan_from is not None:
            delta = pos - self._pan_from
            self._pan_from = pos
            hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
            hbar.setValue(int(hbar.value() - delta.x()))
            vbar.setValue(int(vbar.value() - delta.y()))
            self._fitting = False
            self.view_changed.emit()
            return
        if self._tool is not None and (
            self._tool.hovers or event.buttons() & QtCore.Qt.LeftButton
        ):
            self._tool.move(self._scene_point(pos))
            self._show_tool()
            self.hovered.emit(*self._image_pixel(pos))
            return
        if self._dragging_wipe:
            width = self.image_size()[0]
            if width:
                self.set_wipe_position(self.mapToScene(pos.toPoint()).x() / width)
                self.wipe_moved.emit(self._wipe)
            return
        self.viewport().setCursor(
            QtCore.Qt.SplitHCursor if self._near_wipe(pos) else QtCore.Qt.ArrowCursor
        )
        self.hovered.emit(*self._image_pixel(pos))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        pos = self._pos(event)
        if self._pan_from is not None:
            self._pan_from = None
            self.viewport().setCursor(QtCore.Qt.ArrowCursor)
            return
        if self._dragging_wipe:
            self._dragging_wipe = False
            return
        if self._tool is not None and event.button() == QtCore.Qt.LeftButton:
            if self._tool.release(self._scene_point(pos)):
                self._tool_done()
            else:
                self._show_tool()
            return
        if self._press is not None and event.button() == QtCore.Qt.LeftButton:
            moved = (pos - self._press).manhattanLength()
            self._press = None
            if moved <= QtWidgets.QApplication.startDragDistance():
                self.overlay_clicked.emit(self.overlay_at(pos))
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self._tool is not None and event.button() == QtCore.Qt.LeftButton:
            if self._tool.finish():
                self._tool_done()
            return
        if event.button() == QtCore.Qt.LeftButton:
            self.fit()
            self.view_changed.emit()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered.emit(-1, -1)
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._tool is not None and event.key() == QtCore.Qt.Key_Escape:
            self.set_tool(None)
            event.accept()
            return
        if self._tool is not None and event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if self._tool.finish():
                self._tool_done()
            event.accept()
            return
        if event.key() == QtCore.Qt.Key_Space and not event.isAutoRepeat():
            self._space = True
        event.ignore()  # a parent may want Space too (a comparison's blink)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == QtCore.Qt.Key_Space and not event.isAutoRepeat():
            self._space = False
        event.ignore()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fitting:
            self.fit()
