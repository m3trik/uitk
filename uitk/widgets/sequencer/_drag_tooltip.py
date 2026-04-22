# !/usr/bin/python
# coding=utf-8
"""Floating scene-text that tracks the cursor during timeline drags.

Centralises the "show the current frame next to the cursor while dragging"
pattern used by keyframes, markers, clip move/resize handles, gap overlays,
and range-highlight handles.

Typical use::

    self._drag_tooltip = FrameTooltip()

    def mousePressEvent(self, event):
        ...
        self._drag_tooltip.show(self.scene(), event.scenePos(),
                                label=FrameTooltip.format_frame(self._start),
                                color="#88bbff")

    def mouseMoveEvent(self, event):
        ...
        self._drag_tooltip.update(event.scenePos(),
                                  label=FrameTooltip.format_frame(self._start))

    def mouseReleaseEvent(self, event):
        ...
        self._drag_tooltip.hide()
"""
from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets


class FrameTooltip:
    """Floating ``QGraphicsSimpleTextItem`` that tracks the cursor.

    Used by any timeline handle drag to show the current frame (or custom
    label) beside the cursor.  One instance per draggable item is the
    normal pattern — ``show`` is safe to call repeatedly; it recreates the
    underlying scene item so stale items never linger.
    """

    _OFFSET_X = 10
    _OFFSET_Y = -18

    def __init__(
        self,
        default_color: str = "#dddddd",
        point_size: int = 8,
        bold: bool = True,
    ):
        self._item: Optional[QtWidgets.QGraphicsSimpleTextItem] = None
        self._default_color = QtGui.QColor(default_color)
        self._point_size = point_size
        self._bold = bold

    @staticmethod
    def format_frame(t: float) -> str:
        """Format a frame value — integer when exact, one decimal otherwise."""
        t = float(t)
        return str(int(t)) if t == int(t) else f"{t:.1f}"

    def show(
        self,
        scene: Optional[QtWidgets.QGraphicsScene],
        scene_pos: QtCore.QPointF,
        label: str = "",
        color: Optional[str] = None,
    ) -> None:
        """Attach the tooltip to *scene* at *scene_pos*.

        Safe to call when a tooltip is already visible — the prior item is
        removed first.
        """
        self.hide()
        if scene is None:
            return
        self._item = QtWidgets.QGraphicsSimpleTextItem()
        self._item.setZValue(100)
        font = self._item.font()
        font.setPointSize(self._point_size)
        font.setBold(self._bold)
        self._item.setFont(font)
        brush_color = QtGui.QColor(color) if color else self._default_color
        self._item.setBrush(brush_color)
        scene.addItem(self._item)
        self.update(scene_pos, label=label)

    def update(
        self,
        scene_pos: QtCore.QPointF,
        label: Optional[str] = None,
        color: Optional[str] = None,
    ) -> None:
        """Reposition (and optionally retext/recolor) the tooltip."""
        if self._item is None:
            return
        if label is not None:
            self._item.setText(label)
        if color is not None:
            self._item.setBrush(QtGui.QColor(color))
        self._item.setPos(
            scene_pos.x() + self._OFFSET_X, scene_pos.y() + self._OFFSET_Y
        )

    def hide(self) -> None:
        """Remove the tooltip from the scene, if any."""
        if self._item is not None:
            scene = self._item.scene()
            if scene:
                scene.removeItem(self._item)
            self._item = None

    def is_visible(self) -> bool:
        return self._item is not None
