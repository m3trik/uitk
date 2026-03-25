# !/usr/bin/python
# coding=utf-8
"""ClipItem — draggable, resizable clip rectangle on the timeline."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from qtpy import QtWidgets, QtGui, QtCore

if TYPE_CHECKING:
    from uitk.widgets.sequencer._timeline import TimelineView

from uitk.widgets.sequencer._data import (
    ClipData,
    _MIN_POINT_CLIP_WIDTH,
    _MIN_CLIP_DURATION,
    _HANDLE_WIDTH,
    _styled_menu,
    _menu_exec_pos,
)


class ClipItem(QtWidgets.QGraphicsRectItem):
    """A draggable, resizable rectangle representing one clip on the timeline."""

    def __init__(self, clip_data: ClipData, timeline: "TimelineView"):
        super().__init__()
        self._data = clip_data
        self._timeline = timeline
        self._drag_mode = None  # "move", "resize_left", "resize_right"
        self._drag_origin_x = 0.0
        self._drag_origin_start = 0.0
        self._drag_origin_duration = 0.0
        self._drag_peers: list = []  # [(ClipItem, original_start), ...]
        self._waveform_pixmap: Optional[QtGui.QPixmap] = None
        self._waveform_pixmap_size: Optional[tuple] = None
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        # Dimmed (non-active shot) clips sit behind active clips
        if clip_data.data.get("dimmed"):
            self.setZValue(-0.5)
        # Sub-row clips show label as tooltip instead of inline text
        if clip_data.sub_row and clip_data.label:
            self.setToolTip(clip_data.label)
        self._sync_geometry()

    def _snap(self, value: float) -> float:
        """Snap *value* to the nearest grid interval if snapping is enabled.

        Holding **Ctrl** while dragging forces the interval to 1 (per-frame).
        """
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ControlModifier:
            return round(value)
        interval = self._timeline.parent_sequencer.snap_interval
        if interval > 0:
            return round(value / interval) * interval
        return value

    # -- data access --------------------------------------------------------
    @property
    def clip_data(self) -> ClipData:
        return self._data

    # -- geometry sync ------------------------------------------------------
    def _sync_geometry(self):
        """Recalculate rect from data using the timeline's mapper."""
        tl = self._timeline
        x = tl.time_to_x(self._data.start)
        w = tl.time_to_x(self._data.start + self._data.duration) - x
        widget = tl.parent_sequencer
        track_y, row_h = widget._row_position(self._data.track_id, self._data.sub_row)
        # Zero-duration (point) clips get a minimum visual width, centered
        if w < _MIN_POINT_CLIP_WIDTH:
            x -= (_MIN_POINT_CLIP_WIDTH - w) / 2.0
            w = _MIN_POINT_CLIP_WIDTH
        new_rect = QtCore.QRectF(x, track_y, max(w, 1), row_h)
        # Invalidate waveform cache when width changes (zoom/resize)
        if self.rect().width() != new_rect.width():
            self._waveform_pixmap = None
        self.setRect(new_rect)

    def _track_index(self) -> int:
        widget = self._timeline.parent_sequencer
        for i, td in enumerate(widget._tracks):
            if td.track_id == self._data.track_id:
                return i
        return 0

    def _resolve_color(self) -> QtGui.QColor:
        """Resolve clip color from attributes.

        Uses the attribute color map only when every attribute on the clip
        resolves to the *same* color (e.g. a single-attribute clip or a
        group where all attrs share a color).  Mixed-attribute clips use
        the 'consolidated' color (default white) to indicate that multiple
        attributes are combined.
        """
        attrs = self._data.data.get("attributes")
        if attrs:
            color_map = self._timeline.parent_sequencer.attribute_colors
            matched = {color_map[a] for a in attrs if a in color_map}
            if len(matched) == 1:
                return QtGui.QColor(matched.pop())
            if len(matched) > 1:
                return QtGui.QColor(color_map.get("consolidated", "#FFFFFF"))
        return QtGui.QColor(self._data.color or "#CCCCCC")

    @staticmethod
    def _foreground_for(color: QtGui.QColor) -> QtGui.QColor:
        """Return black or white depending on the background luminance."""
        lum = 0.299 * color.redF() + 0.587 * color.greenF() + 0.114 * color.blueF()
        return QtGui.QColor("#1E1E1E") if lum > 0.55 else QtGui.QColor("#FFFFFF")

    # -- painting -----------------------------------------------------------
    def paint(self, painter: QtGui.QPainter, option, widget=None):
        rect = self.rect()
        color = self._resolve_color()
        if self._data.data.get("dimmed"):
            color = color.darker(250)
        if self.isSelected():
            color = color.lighter(130)

        fg = self._foreground_for(color)

        # Keyframe-overlay mode for sub-row clips with keyframe data:
        # draw a subtle tinted bar + individual key glyphs instead of
        # the default solid block.
        kf_data = self._data.data.get("keyframe_times")
        if self._data.sub_row and kf_data:
            self._paint_keyframes(painter, rect, kf_data, color, fg)
            # Lock indicator still needed on keyframe sub-rows
            if (
                self._data.locked
                and not self._data.data.get("read_only")
                and rect.width() > 14
                and rect.height() > 10
            ):
                self._paint_lock_icon(painter, rect, fg)
            return

        painter.setBrush(color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

        # Status tint overlay (assessment severity from shot manifest)
        status_hex = self._data.data.get("status_color")
        if status_hex:
            sc = QtGui.QColor(status_hex)
            sc.setAlpha(50)
            painter.setBrush(sc)
            painter.drawRect(rect)

        # Waveform overlay (if envelope data is present)
        waveform = self._data.data.get("waveform")
        if waveform and rect.width() > 4:
            self._paint_waveform(painter, rect, waveform, color)

        # Label
        if rect.width() > 30:
            painter.setPen(fg)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            text_rect = rect.adjusted(6, 0, -6, 0)
            painter.drawText(
                text_rect,
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                self._data.label,
            )

        # Lock indicator (skip for read-only clips from non-active shots)
        if (
            self._data.locked
            and not self._data.data.get("read_only")
            and rect.width() > 14
            and rect.height() > 10
        ):
            self._paint_lock_icon(painter, rect, fg)

    def _paint_lock_icon(self, painter, rect, fg=None):
        """Draw a small lock glyph at the right edge of the clip."""
        if fg is None:
            fg = QtGui.QColor("#FFFFFF")
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        # Position at top-right
        ix = rect.right() - 12
        iy = rect.top() + 3
        painter.setPen(QtGui.QPen(fg, 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)
        # Shackle arc
        painter.drawArc(
            QtCore.QRectF(ix + 1, iy, 6, 6),
            0 * 16,
            180 * 16,
        )
        # Body rectangle
        painter.setBrush(fg)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(ix, iy + 4, 8, 6))
        painter.restore()

    def _paint_waveform(self, painter, rect, waveform, base_color):
        """Render a waveform envelope inside the clip rectangle.

        The waveform is pre-rendered to a QPixmap and cached.  The cache
        is invalidated when the clip width changes (zoom/resize).
        """
        n_bins = len(waveform)
        if n_bins == 0:
            return

        w = int(rect.width() - 2)
        h = int(rect.height() - 4)
        if w < 1 or h < 1:
            return

        size_key = (w, h)
        if self._waveform_pixmap is None or self._waveform_pixmap_size != size_key:
            self._waveform_pixmap = self._render_waveform_pixmap(
                waveform, w, h, base_color
            )
            self._waveform_pixmap_size = size_key

        painter.drawPixmap(
            QtCore.QPointF(rect.x() + 1, rect.y() + 2),
            self._waveform_pixmap,
        )

    @staticmethod
    def _render_waveform_pixmap(waveform, w, h, base_color):
        """Pre-render waveform lines into a transparent QPixmap."""
        pixmap = QtGui.QPixmap(w, h)
        pixmap.fill(QtCore.Qt.transparent)

        n_bins = len(waveform)
        cy = h / 2.0

        wave_color = base_color.lighter(170)
        wave_color.setAlpha(200)

        p = QtGui.QPainter(pixmap)
        p.setPen(QtGui.QPen(wave_color, 1))

        for col in range(w):
            idx = min(int(col * n_bins / w), n_bins - 1)
            lo, hi = waveform[idx]
            y_top = cy - hi * (h / 2)
            y_bot = cy - lo * (h / 2)
            p.drawLine(QtCore.QPointF(col, y_top), QtCore.QPointF(col, y_bot))

        p.end()
        return pixmap

    def _paint_keyframes(self, painter, rect, kf_data, color, fg):
        """Draw individual keyframe glyphs on a sub-row clip.

        Parameters
        ----------
        kf_data : list[tuple[float, str]]
            Each entry is ``(time, tangent_type)`` where *tangent_type*
            is a Maya out-tangent string (e.g. ``"spline"``, ``"step"``).
        color : QColor
            Resolved attribute color.
        fg : QColor
            Foreground (text) color contrasting with *color*.
        """
        # Subtle segment background — 35 % opacity tinted bar
        bar_color = QtGui.QColor(color)
        bar_color.setAlpha(90)
        painter.setBrush(bar_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

        dur = self._data.duration
        cy = rect.center().y()
        half = min(rect.height() * 0.35, 5.0)  # half-size of diamond

        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        key_color = QtGui.QColor(color)
        if self.isSelected():
            key_color = key_color.lighter(150)
        painter.setBrush(key_color)
        painter.setPen(QtGui.QPen(fg, 0.6))

        for kf_time, tangent in kf_data:
            # Map keyframe time to local x within the clip rect
            if dur > 1e-6:
                frac = (kf_time - self._data.start) / dur
            else:
                frac = 0.5
            kx = rect.x() + frac * rect.width()
            kx = max(rect.x() + half, min(kx, rect.right() - half))

            if tangent in ("step", "stepnext"):
                # Square glyph for stepped keys
                painter.drawRect(
                    QtCore.QRectF(kx - half, cy - half, half * 2, half * 2)
                )
            else:
                # Diamond glyph for spline/linear/etc
                diamond = QtGui.QPolygonF(
                    [
                        QtCore.QPointF(kx, cy - half),
                        QtCore.QPointF(kx + half, cy),
                        QtCore.QPointF(kx, cy + half),
                        QtCore.QPointF(kx - half, cy),
                    ]
                )
                painter.drawPolygon(diamond)

        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

    # -- hover cursor -------------------------------------------------------
    def hoverMoveEvent(self, event):
        if self._data.locked:
            self.setCursor(QtCore.Qt.ArrowCursor)
            super().hoverMoveEvent(event)
            return
        zone = self._hit_zone(event.pos())
        if zone in ("resize_left", "resize_right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    # -- drag interaction ---------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self._data.locked:
                # Allow selection but prevent drag
                super().mousePressEvent(event)
                return
            self._drag_mode = self._hit_zone(event.pos())
            self._drag_origin_x = event.scenePos().x()
            self._drag_origin_start = self._data.start
            self._drag_origin_duration = self._data.duration
            sq = self._timeline.parent_sequencer
            sq._shift_at_press = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            # Capture peer clips for group move
            self._drag_peers = []
            if self._drag_mode == "move" and self.isSelected():
                for item in self._timeline._scene.selectedItems():
                    if (
                        isinstance(item, ClipItem)
                        and item is not self
                        and not item._data.locked
                    ):
                        self._drag_peers.append((item, item._data.start))
            # Capture pre-drag snapshot for undo
            self._timeline.parent_sequencer._capture_undo()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            return super().mouseMoveEvent(event)

        tl = self._timeline
        dx_time = tl.x_to_time(event.scenePos().x()) - tl.x_to_time(self._drag_origin_x)

        if self._drag_mode == "move":
            new_start = self._snap(max(0.0, self._drag_origin_start + dx_time))
            self._data.start = new_start
            # Move peer clips by the same snapped delta
            snapped_delta = new_start - self._drag_origin_start
            for peer, origin_start in self._drag_peers:
                peer._data.start = max(0.0, origin_start + snapped_delta)
                peer._sync_geometry()
                peer.update()

        elif self._drag_mode == "resize_left":
            new_start = min(
                self._drag_origin_start + dx_time,
                self._drag_origin_start
                + self._drag_origin_duration
                - _MIN_CLIP_DURATION,
            )
            new_start = self._snap(max(0.0, new_start))
            delta = new_start - self._drag_origin_start
            self._data.start = new_start
            self._data.duration = self._drag_origin_duration - delta

        elif self._drag_mode == "resize_right":
            raw_end = self._drag_origin_start + self._drag_origin_duration + dx_time
            snapped_end = self._snap(raw_end)
            new_dur = max(_MIN_CLIP_DURATION, snapped_end - self._data.start)
            self._data.duration = new_dur

        self._sync_geometry()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._drag_mode:
            mode = self._drag_mode
            peers = self._drag_peers
            self._drag_mode = None
            self._drag_peers = []
            self.unsetCursor()
            widget = self._timeline.parent_sequencer
            if mode == "move":
                if peers:
                    moves = [(self._data.clip_id, self._data.start)]
                    for peer, _ in peers:
                        moves.append((peer._data.clip_id, peer._data.start))
                    widget.clips_batch_moved.emit(moves)
                else:
                    widget.clip_moved.emit(self._data.clip_id, self._data.start)
            else:
                widget.clip_resized.emit(
                    self._data.clip_id, self._data.start, self._data.duration
                )
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- context menu -------------------------------------------------------
    def contextMenuEvent(self, event):
        if self._data.data.get("read_only"):
            event.ignore()
            return
        menu = _styled_menu()

        # Lock / Unlock
        if self._data.locked:
            action_lock = menu.addAction("Unlock")
        else:
            action_lock = menu.addAction("Lock")

        # Rename
        action_rename = menu.addAction("Rename")
        if self._data.locked:
            action_rename.setEnabled(False)

        # Extensibility hook — let consumers add domain-specific actions
        widget = self._timeline.parent_sequencer
        widget.clip_menu_requested.emit(menu, self._data.clip_id)

        chosen = menu.exec_(_menu_exec_pos(event))
        if chosen == action_lock:
            self._data.locked = not self._data.locked
            self.update()
            widget.clip_locked.emit(self._data.clip_id, self._data.locked)
        elif chosen == action_rename:
            self._start_inline_rename()

    # -- double-click to rename --------------------------------------------
    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self._data.locked:
                return
            self._start_inline_rename()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _start_inline_rename(self):
        """Spawn a QLineEdit proxy widget over the clip for inline renaming."""
        rect = self.rect()
        edit = QtWidgets.QLineEdit()
        edit.setText(self._data.label)
        edit.selectAll()
        edit.setFrame(False)
        edit.setStyleSheet(
            "background:#333; color:#FFF; padding:0 4px; font-size:10px;"
        )
        edit.setFixedHeight(int(rect.height()))

        proxy = self.scene().addWidget(edit)
        proxy.setPos(rect.x(), rect.y())
        proxy.setZValue(100)
        edit.setFixedWidth(max(int(rect.width()), 60))
        edit.setFocus()

        finished = [False]

        def _finish():
            if finished[0]:
                return
            finished[0] = True
            new_label = edit.text()
            self._data.label = new_label
            self.update()
            widget = self._timeline.parent_sequencer
            widget.clip_renamed.emit(self._data.clip_id, new_label)
            if proxy.scene():
                proxy.scene().removeItem(proxy)

        edit.editingFinished.connect(_finish)

    # -- utilities ----------------------------------------------------------
    def _hit_zone(self, pos) -> str:
        rect = self.rect()
        local_x = pos.x() - rect.x()
        if local_x <= _HANDLE_WIDTH and self._data.data.get("resizable_left", True):
            return "resize_left"
        elif local_x >= rect.width() - _HANDLE_WIDTH and self._data.data.get(
            "resizable_right", True
        ):
            return "resize_right"
        return "move"
