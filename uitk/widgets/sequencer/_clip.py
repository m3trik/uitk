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
    hatch_brush,
    HATCH_DENSE,
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

        # Curve-preview mode for sub-row clips: draw a mini normalised
        # graph-editor view (Bézier curves + key dots).
        preview = self._data.data.get("curve_preview")
        if self._data.sub_row and preview:
            self._paint_curve_preview(painter, rect, preview, color, fg)
            # Lock indicator still needed on sub-rows
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

        # Interpolated-motion overlay (no physical keys in this shot)
        if self._data.data.get("interpolated"):
            hc = QtGui.QColor(color.darker(180))
            hc.setAlpha(90)
            painter.fillRect(rect, hatch_brush(hc, HATCH_DENSE))

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

        # Label — center label (abbreviated attrs) always shown;
        # edge frame numbers only appear during drag operations.
        lbl_center = self._data.data.get("label_center", "")
        w = rect.width()
        dragging = self._drag_mode is not None
        has_label = lbl_center or dragging or self._data.label
        if has_label:
            painter.setPen(fg)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            fm = painter.fontMetrics()
            pad = 4
            text_rect = rect.adjusted(pad, 0, -pad, 0)
            tw = text_rect.width()

            left_used = 0.0
            right_used = 0.0

            # Edge frame numbers — only during drag/resize
            if dragging and w > 40:
                lbl_left = str(round(self._data.start))
                lbl_right = str(round(self._data.start + self._data.duration))
                left_w = fm.horizontalAdvance(lbl_left)
                left_used = left_w + pad
                left_rect = QtCore.QRectF(
                    text_rect.left(),
                    text_rect.top(),
                    min(left_w, tw * 0.4),
                    text_rect.height(),
                )
                painter.drawText(
                    left_rect,
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                    lbl_left,
                )
                right_w = fm.horizontalAdvance(lbl_right)
                right_used = right_w + pad
                right_rect = QtCore.QRectF(
                    text_rect.right() - min(right_w, tw * 0.4),
                    text_rect.top(),
                    min(right_w, tw * 0.4),
                    text_rect.height(),
                )
                painter.drawText(
                    right_rect,
                    QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight,
                    lbl_right,
                )

            # Center label — during drag show frame count, otherwise
            # show abbreviated attribute names.
            center_text = lbl_center
            if dragging:
                center_text = f"{round(self._data.duration)}f"
            if center_text and tw > 0:
                avail = tw - left_used - right_used
                if avail > fm.horizontalAdvance(".."):
                    center_rect = QtCore.QRectF(
                        text_rect.left() + left_used,
                        text_rect.top(),
                        avail,
                        text_rect.height(),
                    )
                    elided = fm.elidedText(center_text, QtCore.Qt.ElideRight, int(avail))
                    painter.drawText(
                        center_rect,
                        QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter,
                        elided,
                    )
            elif not lbl_center and not dragging and w > 30 and self._data.label:
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

    def _paint_curve_preview(self, painter, rect, preview, color, fg):
        """Draw a normalised mini graph-editor view inside a sub-row clip.

        Parameters
        ----------
        preview : dict
            ``{keys, segments, val_min, val_max}`` produced by
            ``build_curve_preview`` on the controller side.
        color : QColor
            Resolved attribute colour.
        fg : QColor
            Foreground (text) colour contrasting with *color*.
        """
        keys = preview.get("keys", [])
        segments = preview.get("segments", [])
        val_min = preview.get("val_min", 0.0)
        val_max = preview.get("val_max", 1.0)

        # --- background tint ---
        bar_color = QtGui.QColor(color)
        bar_color.setAlpha(60)
        painter.setBrush(bar_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

        if not segments:
            return

        # --- coordinate mapping helpers ---
        pad = rect.height() * 0.15
        y_top = rect.top() + pad
        y_bot = rect.bottom() - pad
        y_span = y_bot - y_top

        dur = self._data.duration
        val_range = val_max - val_min
        is_flat = val_range < 1e-9
        if is_flat:
            val_range = 1.0

        def map_x(t):
            if dur > 1e-6:
                frac = (t - self._data.start) / dur
            else:
                frac = 0.5
            return rect.x() + frac * rect.width()

        def map_y(v):
            if is_flat:
                return y_top + y_span * 0.5
            # Invert: high values → top of rect
            frac = (v - val_min) / val_range
            return y_bot - frac * y_span

        # --- draw curve path (clip to rect to contain bounding keys) ---
        painter.save()
        painter.setClipRect(rect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        curve_color = QtGui.QColor(color)
        curve_color.setAlpha(180)
        painter.setPen(QtGui.QPen(curve_color, 1.2))
        painter.setBrush(QtCore.Qt.NoBrush)

        path = QtGui.QPainterPath()
        first_seg = segments[0]
        path.moveTo(map_x(first_seg["t0"]), map_y(first_seg["v0"]))

        for seg in segments:
            x1 = map_x(seg["t1"])
            y1 = map_y(seg["v1"])
            ot = seg.get("out_type", "spline")
            cp1 = seg.get("cp1")
            cp2 = seg.get("cp2")

            if ot == "step":
                # Hold value, then jump at next key
                path.lineTo(x1, map_y(seg["v0"]))
                path.lineTo(x1, y1)
            elif ot == "stepnext":
                # Jump to next value immediately, then hold
                x0 = map_x(seg["t0"])
                path.lineTo(x0, y1)
                path.lineTo(x1, y1)
            elif ot == "linear" or cp1 is None or cp2 is None:
                path.lineTo(x1, y1)
            else:
                # Cubic Bézier via control points
                path.cubicTo(
                    map_x(cp1[0]),
                    map_y(cp1[1]),
                    map_x(cp2[0]),
                    map_y(cp2[1]),
                    x1,
                    y1,
                )

        painter.drawPath(path)

        # --- draw key dots ---
        dot_r = min(rect.height() * 0.18, 3.5)
        key_color = QtGui.QColor(color)
        if self.isSelected():
            key_color = key_color.lighter(150)
        painter.setBrush(key_color)
        painter.setPen(QtGui.QPen(fg, 0.6))

        for t, v in keys:
            kx = map_x(t)
            ky = map_y(v)
            painter.drawEllipse(QtCore.QPointF(kx, ky), dot_r, dot_r)

        painter.restore()

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
            self.update()  # repaint to show drag frame labels
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
            self.update()  # repaint to hide drag frame labels
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
