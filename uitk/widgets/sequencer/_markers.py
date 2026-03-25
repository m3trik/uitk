# !/usr/bin/python
# coding=utf-8
"""MarkerItem — named marker on the timeline with drag and context menu."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import (
    MarkerData,
    _RULER_HEIGHT,
    _styled_menu,
    _menu_exec_pos,
)

_MARKER_TRI_SIZE = 8  # size of the triangle pennant in pixels


class MarkerItem(QtWidgets.QGraphicsItem):
    """A named marker on the timeline: triangle at the ruler + dashed line."""

    def __init__(self, marker_data: MarkerData, timeline: "TimelineView"):
        super().__init__()
        self._data = marker_data
        self._timeline = timeline
        self._drag_active = False
        self._drag_origin_x = 0.0
        self._drag_origin_time = 0.0
        self._drag_tooltip: Optional[QtWidgets.QGraphicsSimpleTextItem] = None
        self.setZValue(15)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setOpacity(marker_data.opacity)
        if marker_data.note:
            self.setToolTip(marker_data.note)
        self.sync()

    @property
    def marker_data(self) -> MarkerData:
        return self._data

    # -- geometry -----------------------------------------------------------

    def boundingRect(self) -> QtCore.QRectF:
        x = self._timeline.time_to_x(self._data.time)
        return QtCore.QRectF(
            x - _MARKER_TRI_SIZE,
            0,
            _MARKER_TRI_SIZE * 2,
            10000,
        )

    def shape(self) -> QtGui.QPainterPath:
        x = self._timeline.time_to_x(self._data.time)
        path = QtGui.QPainterPath()
        path.addRect(x - _MARKER_TRI_SIZE, 0, _MARKER_TRI_SIZE * 2, _RULER_HEIGHT)
        return path

    def sync(self):
        self.prepareGeometryChange()

    # -- painting -----------------------------------------------------------

    _LINE_STYLES = {
        "dashed": QtCore.Qt.DashLine,
        "solid": QtCore.Qt.SolidLine,
        "dotted": QtCore.Qt.DotLine,
    }

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        color = QtGui.QColor(self._data.color)
        x = self._timeline.time_to_x(self._data.time)
        style = self._data.style

        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Head glyph at the ruler
        if style == "diamond":
            half = _MARKER_TRI_SIZE / 2
            cy = _RULER_HEIGHT - _MARKER_TRI_SIZE / 2
            diamond = QtGui.QPolygonF(
                [
                    QtCore.QPointF(x, cy - half),
                    QtCore.QPointF(x + half, cy),
                    QtCore.QPointF(x, cy + half),
                    QtCore.QPointF(x - half, cy),
                ]
            )
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPolygon(diamond)
        elif style == "line":
            painter.setPen(QtGui.QPen(color, 2))
            painter.drawLine(
                QtCore.QPointF(x, _RULER_HEIGHT - _MARKER_TRI_SIZE),
                QtCore.QPointF(x, _RULER_HEIGHT),
            )
        elif style == "bracket":
            bh = _MARKER_TRI_SIZE
            bw = 4
            painter.setPen(QtGui.QPen(color, 1.5))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(
                QtCore.QPointF(x - bw, _RULER_HEIGHT - bh),
                QtCore.QPointF(x - bw, _RULER_HEIGHT),
            )
            painter.drawLine(
                QtCore.QPointF(x - bw, _RULER_HEIGHT),
                QtCore.QPointF(x + bw, _RULER_HEIGHT),
            )
            painter.drawLine(
                QtCore.QPointF(x + bw, _RULER_HEIGHT),
                QtCore.QPointF(x + bw, _RULER_HEIGHT - bh),
            )
        else:  # triangle (default)
            tri = QtGui.QPolygonF(
                [
                    QtCore.QPointF(x, _RULER_HEIGHT),
                    QtCore.QPointF(
                        x - _MARKER_TRI_SIZE / 2, _RULER_HEIGHT - _MARKER_TRI_SIZE
                    ),
                    QtCore.QPointF(
                        x + _MARKER_TRI_SIZE / 2, _RULER_HEIGHT - _MARKER_TRI_SIZE
                    ),
                ]
            )
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPolygon(tri)

        # Vertical line below ruler
        qt_line = self._LINE_STYLES.get(self._data.line_style)
        if qt_line is not None:
            pen = QtGui.QPen(color, 1, qt_line)
            painter.setPen(pen)
            scene_h = self._timeline._scene.height() if self._timeline._scene else 2000
            painter.drawLine(
                QtCore.QPointF(x, _RULER_HEIGHT),
                QtCore.QPointF(x, scene_h),
            )

        # Optional note label beside the head
        if self._data.note:
            painter.setPen(color)
            font = painter.font()
            font.setPointSize(7)
            painter.setFont(font)
            label = self._data.note[:8]
            painter.drawText(
                QtCore.QPointF(x + _MARKER_TRI_SIZE / 2 + 2, _RULER_HEIGHT - 2),
                label,
            )

    # -- hover --------------------------------------------------------------

    def hoverEnterEvent(self, event):
        if self._data.draggable:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag (horizontal only) ---------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._data.draggable:
            self._drag_active = True
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_time = self._data.time
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            self._show_drag_tooltip(event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._drag_active:
            return super().mouseMoveEvent(event)
        tl = self._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(self._drag_origin_x)
        new_time = max(0.0, self._drag_origin_time + dx_time)
        modifiers = event.modifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            new_time = round(new_time)
        else:
            interval = tl.parent_sequencer.snap_interval
            if interval > 0:
                new_time = round(new_time / interval) * interval
        self._data.time = new_time
        self.sync()
        self.update()
        self._update_drag_tooltip(event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._drag_active:
            self._drag_active = False
            self.unsetCursor()
            self._hide_drag_tooltip()
            self.sync()
            self.update()
            widget = self._timeline.parent_sequencer
            widget.marker_moved.emit(self._data.marker_id, self._data.time)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.contextMenuEvent(event)
        else:
            super().mouseDoubleClickEvent(event)

    # -- drag tooltip -------------------------------------------------------

    def _show_drag_tooltip(self, scene_pos):
        self._drag_tooltip = QtWidgets.QGraphicsSimpleTextItem()
        self._drag_tooltip.setZValue(100)
        font = self._drag_tooltip.font()
        font.setPointSize(8)
        font.setBold(True)
        self._drag_tooltip.setFont(font)
        self._drag_tooltip.setBrush(QtGui.QColor(self._data.color))
        if self.scene():
            self.scene().addItem(self._drag_tooltip)
        self._update_drag_tooltip(scene_pos)

    def _update_drag_tooltip(self, scene_pos):
        if self._drag_tooltip is None:
            return
        t = self._data.time
        label = str(int(t)) if t == int(t) else f"{t:.1f}"
        self._drag_tooltip.setText(label)
        self._drag_tooltip.setPos(scene_pos.x() + 10, scene_pos.y() - 18)

    def _hide_drag_tooltip(self):
        if self._drag_tooltip is not None:
            if self._drag_tooltip.scene():
                self._drag_tooltip.scene().removeItem(self._drag_tooltip)
            self._drag_tooltip = None

    # -- context menu -------------------------------------------------------

    def contextMenuEvent(self, event):
        widget = self._timeline.parent_sequencer
        menu = _styled_menu()

        # Inline note editor
        note_edit = QtWidgets.QLineEdit(self._data.note)
        note_edit.setPlaceholderText("Note")
        note_edit.setFixedWidth(140)
        note_action = QtWidgets.QWidgetAction(menu)
        note_action.setDefaultWidget(note_edit)
        menu.addAction(note_action)

        # Inline time editor
        time_edit = QtWidgets.QLineEdit(f"{self._data.time:.1f}")
        time_edit.setPlaceholderText("Time")
        time_edit.setFixedWidth(140)
        time_action = QtWidgets.QWidgetAction(menu)
        time_action.setDefaultWidget(time_edit)
        menu.addAction(time_action)

        menu.addSeparator()

        # Color picker
        color_action = menu.addAction(f"Color: {self._data.color}")

        # Style submenu
        style_menu = menu.addMenu("Style")
        for s in ("triangle", "diamond", "line", "bracket"):
            a = style_menu.addAction(s.capitalize())
            a.setCheckable(True)
            a.setChecked(s == self._data.style)
            a.setData(s)

        # Line style submenu
        ls_menu = menu.addMenu("Line")
        for ls in ("dashed", "solid", "dotted", "none"):
            a = ls_menu.addAction(ls.capitalize())
            a.setCheckable(True)
            a.setChecked(ls == self._data.line_style)
            a.setData(ls)

        # Draggable toggle
        drag_action = menu.addAction("Draggable")
        drag_action.setCheckable(True)
        drag_action.setChecked(self._data.draggable)

        menu.addSeparator()
        remove_action = menu.addAction("Remove Marker")

        # Close the menu when Enter is pressed in either line edit
        note_edit.returnPressed.connect(menu.close)
        time_edit.returnPressed.connect(menu.close)

        chosen = menu.exec_(event.screenPos())

        # Apply edits regardless of which action closed the menu
        new_note = note_edit.text()
        if new_note != self._data.note:
            self._data.note = new_note
            self.setToolTip(new_note)
            self.update()
            widget.marker_changed.emit(self._data.marker_id)

        try:
            new_time = float(time_edit.text())
        except ValueError:
            new_time = self._data.time
        if abs(new_time - self._data.time) > 1e-6:
            self._data.time = max(0.0, new_time)
            self.sync()
            self.update()
            widget.marker_moved.emit(self._data.marker_id, self._data.time)

        if chosen == remove_action:
            widget.remove_marker(self._data.marker_id)
        elif chosen == color_action:
            c = QtWidgets.QColorDialog.getColor(
                QtGui.QColor(self._data.color), None, "Marker Color"
            )
            if c.isValid():
                self._data.color = c.name()
                self.update()
                widget.marker_changed.emit(self._data.marker_id)
        elif chosen == drag_action:
            self._data.draggable = drag_action.isChecked()
            widget.marker_changed.emit(self._data.marker_id)
        elif chosen is not None and chosen.parent() == style_menu:
            self._data.style = chosen.data()
            self.sync()
            self.update()
            widget.marker_changed.emit(self._data.marker_id)
        elif chosen is not None and chosen.parent() == ls_menu:
            self._data.line_style = chosen.data()
            self.update()
            widget.marker_changed.emit(self._data.marker_id)
